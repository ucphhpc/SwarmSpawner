OWNER=rasmunk
IMAGE=swarmspawner
TAG=edge

.PHONY: build

all: clean build push

build:
	python3 setup.py sdist bdist_wheel
	docker build -t ${OWNER}/${IMAGE}:${TAG} .

clean:
	rm -fr dist build jhub_swarmspawner.egg-info
	docker rmi -f ${OWNER}/${IMAGE}:${TAG}

push:
	docker push ${OWNER}/${IMAGE}:${TAG}
