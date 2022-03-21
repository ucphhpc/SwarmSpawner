OWNER=ucphhpc
IMAGE=swarmspawner
TAG=edge
ARGS=

.PHONY: build

all: clean build push

build:
	python3 setup.py sdist bdist_wheel
	docker build -t ${OWNER}/${IMAGE}:${TAG} $(ARGS) .

clean:
	rm -fr dist build jhub_swarmspawner.egg-info
	docker rmi -f ${OWNER}/${IMAGE}:${TAG}

push:
	docker push ${OWNER}/${IMAGE}:${TAG}

installtests:
	pip3 install -r tests/requirements.txt

# The tests requires access to the docker socket
test: 
	$(MAKE) build
	pytest -s -v tests/
