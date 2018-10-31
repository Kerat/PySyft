FROM python:3.6-alpine

COPY ./docs \
     ./syft \
     ./test \
     ./Makefile \
     ./README.md \
     ./requirements.txt \
     ./setup.py \
     /PySyft/

RUN apk add \
    --repository http://dl-4.alpinelinux.org/alpine/edge/testing \
    --no-cache \
    --virtual .build-deps \
    build-base \
    jpeg-dev \
    hdf5-dev \
 && apk add zeromq-dev \
 && pip install --no-cache-dir jupyter \
 && pip install https://storage.googleapis.com/tensorflow/linux/cpu/tensorflow-1.11.0-cp36-cp36m-linux_x86_64.whl \
 && pip install http://download.pytorch.org/whl/cpu/torch-0.3.1-cp36-cp36m-linux_x86_64.whl \
 && pip install torchvision \
 && cd /PySyft \
 && python setup.py install \
 && rm -r /root/.cache/pip \
 && jupyter notebook --generate-config \
 && jupyter nbextension enable --py --sys-prefix widgetsnbextension \
 && python -m ipykernel.kernelspec \
 && apk del .build-deps \
 && rm -rf /var/cache/apk/* \
 && rm -rf /tmp/* \
 && rm -rf /PySyft/examples \
 && mkdir /notebooks

WORKDIR /notebooks

ENTRYPOINT ["jupyter", "notebook", "--ip=0.0.0.0", "--port=8888", "--Notebook.open_browser=False", "--NotebookApp.token=''", "--allow-root"]
