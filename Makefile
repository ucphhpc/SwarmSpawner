OWNER=ucphhpc
IMAGE=swarmspawner
TAG=edge

.PHONY: build

all: clean build push

build:
	docker build -t ${OWNER}/${IMAGE}:${TAG} .

clean:
	docker rmi -f ${OWNER}/${IMAGE}:${TAG}

push:
	docker push ${OWNER}/${IMAGE}:${TAG}

# The tests requires access to the docker socket
test:
	pytest -s -v tests/
