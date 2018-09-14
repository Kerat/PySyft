import torch
import syft as sy
from ..core.frameworks.torch.tensor import _GeneralizedPointerTensor
BASE = 2
KAPPA = 3  # ~29 bits

# TODO set these intelligently
PRECISION_INTEGRAL = 2
PRECISION_FRACTIONAL = 0
PRECISION = PRECISION_INTEGRAL + PRECISION_FRACTIONAL
BOUND = BASE ** PRECISION

# Q field
Q_BITS = 31#32#62
field = 2 ** Q_BITS  # < 63 bits
Q_MAXDEGREE = 1


def encode(rational, precision_fractional=PRECISION_FRACTIONAL, mod=field):
    upscaled = (rational * BASE ** precision_fractional).long()
    field_element = upscaled % mod
    return field_element


def decode(field_element, precision_fractional=PRECISION_FRACTIONAL, mod=field):
    neg_values = field_element.gt(mod)
    # pos_values = field_element.le(field)
    # upscaled = field_element*(neg_valuese+pos_values)
    field_element[neg_values] = mod - field_element[neg_values]
    rational = field_element.float() / BASE ** precision_fractional
    return rational


def share(secret, mod=field):
    first = torch.LongTensor(secret.shape).random_(mod)
    second = (secret - first) % mod
    return first, second


def reconstruct(shares, mod=field):
    return sum(shares) % mod


def swap_shares(shares):
    ptd = shares.child.pointer_tensor_dict
    alice, bob = list(ptd.keys())
    new_alice = (ptd[alice]+0)
    new_bob = (ptd[bob]+0)
    new_alice.send(bob)
    new_bob.send(alice)

    return _GeneralizedPointerTensor({alice:new_bob,bob:new_alice}).on(sy.LongTensor([]))


def truncate(x, interface, amount=PRECISION_FRACTIONAL, mod=field):
    if (interface.get_party() == 0):
        return (x / BASE ** amount) % mod
    return (mod - ((mod - x) / BASE ** amount)) % mod


def public_add(x, y, interface):
    if (interface.get_party() == 0):
        return (x + y)
    elif (interface.get_party() == 1):
        return x


def spdz_add(a, b, mod=field):
    c = a + b
    return c % mod


def spdz_neg(a, mod=field):
    return (mod - a) % mod


def spdz_mul(x, y, workers, mod=field):
    if x.shape != y.shape:
        raise ValueError()
    shape = x.shape
    alice, bob = workers
    triple = generate_mul_triple_communication(shape, alice, bob)
    a, b, c = triple

    d = (x - a) % mod
    e = (y - b) % mod

    delta = d.child.sum_get() % mod
    epsilon = e.child.sum_get() % mod

    delta = delta.broadcast(workers)
    epsilon = epsilon.broadcast(workers)

    n = len(workers)
    z = (c
         + (delta * b) % mod
         + (epsilon * a) % mod
         + ((epsilon * delta) % mod) / n
         ) % mod
    return z


def spdz_matmul(x, y, interface, mod=field):
    x_height = x.shape[0]
    if len(x.shape) != 1:
        x_width = x.shape[1]
    else:
        x_width = 1

    y_height = y.shape[0]
    if len(y.shape) != 1:
        y_width = y.shape[1]
    else:
        y_width = 1

    assert x_width == y_height, 'dimension mismatch: %r != %r' % (
        x_width, y_height,
    )

    r, s, t = generate_matmul_triple_communication(
        x_height, y_width, x_width, interface,
    )

    rho_local = (x - r) % mod
    sigma_local = (y - s) % mod

    # Communication
    rho_other = swap_shares(rho_local, interface)
    sigma_other = swap_shares(sigma_local, interface)

    # They both add up the shares locally
    rho = reconstruct([rho_local, rho_other])
    sigma = reconstruct([sigma_local, sigma_other])

    r_sigma = r * sigma
    rho_s = rho * s

    share = r_sigma + rho_s + t

    rs = rho * sigma

    share = public_add(share, rs, interface)
    share = truncate(share, interface)

    # we assume we need to mask the result for a third party crypto provider
    u = generate_zero_shares_communication(alice, bob, *share.shape)
    return spdz_add(share, u)


def spdz_sigmoid(x, interface):
    W0, W1, W3, W5 = generate_sigmoid_shares_communication(x, interface)
    x2 = spdz_mul(x, x, interface)
    x3 = spdz_mul(x, x2, interface)
    x5 = spdz_mul(x3, x2, interface)
    temp5 = spdz_mul(x5, W5, interface)
    temp3 = spdz_mul(x3, W3, interface)
    temp1 = spdz_mul(x, W1, interface)
    temp53 = spdz_add(temp5, temp3)
    temp531 = spdz_add(temp53, temp1)
    return spdz_add(W0, temp531)


def generate_mul_triple(shape, mod=field):
    r = torch.LongTensor(shape).random_(mod)
    s = torch.LongTensor(shape).random_(mod)
    t = r * s
    return r, s, t


def generate_mul_triple_communication(shape, alice, bob):
        r, s, t = generate_mul_triple(shape)

        r_alice, r_bob = share(r)
        s_alice, s_bob = share(s)
        t_alice, t_bob = share(t)

        r_alice.send(alice)
        r_bob.send(bob)

        s_alice.send(alice)
        s_bob.send(bob)

        t_alice.send(alice)
        t_bob.send(bob)

        gp_r = _GeneralizedPointerTensor({alice: r_alice.child, bob: r_bob.child}).on(r)
        gp_s = _GeneralizedPointerTensor({alice: s_alice.child, bob: s_bob.child}).on(s)
        gp_t = _GeneralizedPointerTensor({alice: t_alice.child, bob: t_bob.child}).on(t)
        triple = [gp_r, gp_s, gp_t]
        return triple


def generate_zero_shares_communication(alice, bob, *sizes):
    zeros = torch.zeros(*sizes)
    u_alice, u_bob = share(zeros)
    u_alice.send(alice)
    u_bob.send(bob)
    u_gp = _GeneralizedPointerTensor({alice: u_alice.child, bob: u_bob.child})
    return u_gp


def generate_matmul_triple(m, n, k, mod=field):
    r = torch.LongTensor(m, k).random_(mod)
    s = torch.LongTensor(k, n).random_(mod)
    t = r * s
    return r, s, t


def generate_matmul_triple_communication(m, n, k, interface):
    if (interface.get_party() == 0):
        r, s, t = generate_matmul_triple(m, n, k)
        r_alice, r_bob = share(r)
        s_alice, s_bob = share(s)
        t_alice, t_bob = share(t)

        swap_shares(r_bob, interface)
        swap_shares(s_bob, interface)
        swap_shares(t_bob, interface)

        triple_alice = [r_alice, s_alice, t_alice]
        return triple_alice
    elif (interface.get_party() == 1):
        r_bob = swap_shares(torch.LongTensor(m, k).zero_(), interface)
        s_bob = swap_shares(torch.LongTensor(k, n).zero_(), interface)
        t_bob = swap_shares(torch.LongTensor(m, n).zero_(), interface)
        triple_bob = [r_bob, s_bob, t_bob]
        return triple_bob


def generate_sigmoid_shares_communication(x, interface):
    if (interface.get_party() == 0):
        W0 = encode(torch.FloatTensor(x.shape).one_() * 1 / 2)
        W1 = encode(torch.FloatTensor(x.shape).one_() * 1 / 4)
        W3 = encode(torch.FloatTensor(x.shape).one_() * -1 / 48)
        W5 = encode(torch.FloatTensor(x.shape).one_() * 1 / 480)

        W0_alice, W0_bob = share(W0)
        W1_alice, W1_bob = share(W1)
        W3_alice, W3_bob = share(W3)
        W5_alice, W5_bob = share(W5)

        swap_shares(W0_bob, interface)
        swap_shares(W1_bob, interface)
        swap_shares(W3_bob, interface)
        swap_shares(W5_bob, interface)

        quad_alice = [W0_alice, W1_alice, W3_alice, W5_alice]
        return quad_alice
    elif (interface.get_party() == 1):
        W0_bob = swap_shares(
            torch.LongTensor(
                x.shape,
            ).zero_(), interface,
        )
        W1_bob = swap_shares(
            torch.LongTensor(
                x.shape,
            ).zero_(), interface,
        )
        W3_bob = swap_shares(
            torch.LongTensor(
                x.shape,
            ).zero_(), interface,
        )
        W5_bob = swap_shares(
            torch.LongTensor(
                x.shape,
            ).zero_(), interface,
        )
        quad_bob = [W0_bob, W1_bob, W3_bob, W5_bob]
        return quad_bob
