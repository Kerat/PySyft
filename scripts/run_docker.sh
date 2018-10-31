#!/usr/bin/env bash
VER=$(docker version 2> /dev/null)
RET=$?
PORT=8888
if [ $RET -eq 127 ]; then
    echo Docker do not seems to be installed.
    exit 1
elif [ $(echo $VER | grep Server | wc -w) -eq 0 ]; then
    echo Docker daemon do not seems to be running.
    exit 1
fi

echo Building image...
docker build --tag pysyft .
if [ $? -ne 0 ]; then
    echo Build failed.
    exit 1
fi
echo Build done! Image size: $(docker images --format {{.Size}} --filter reference=pysyft)

if [ $(docker ps -a | grep My_PySyft | wc -l) -ge 1 ]; then
    echo A PySyft container is already running! Stopping it...
    docker stop My_PySyft
    echo PySyft container stopped!
fi
echo Running PySyft container with name My_PySyft...
docker run -d --rm -p $PORT:8888 --volume=$PWD/examples:/notebooks --name My_PySyft pysyft
sleep 1
if [ $(docker ps -a | grep My_PySyft | wc -l) -ge 1 ]; then
    echo PySyft is running! Open http://localhost:$PORT/ in your web browser
else
    echo Something went wrong on running container.
    exit 1
fi
exit 0

