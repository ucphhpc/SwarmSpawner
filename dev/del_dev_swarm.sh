#!/bin/bash
NETWORK_NAME=jh_dev
MOUNT_PLUGIN=ucphhpc/sshfs:latest

docker network rm $NETWORK_NAME
docker plugin disable $MOUNT_PLUGIN
docker plugin rm $MOUNT_PLUGIN
docker swarm leave --force