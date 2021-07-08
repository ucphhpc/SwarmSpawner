#!/bin/bash
ADDR=192.168.1.73
NETWORK_NAME=jh_dev
MOUNT_PLUGIN=nielsbohr/sshfs:latest


docker plugin install -y $MOUNT_PLUGIN
docker swarm init --advertise-addr $ADDR
docker network create --driver overlay $NETWORK_NAME
