OWNER=ucphhpc
IMAGE=swarmspawner
TAG=edge
ARGS=

VENV_NAME?=venv
ACTIVATE_FILE?=${VENV_NAME}/bin/activate
PYTHON=${VENV_NAME}/bin/python3
PACKAGE_NAME=jhub_swarmspawner


.PHONY: dockerbuild dockerclean dockerpush clean dist distclean maintainer-clean
.PHONY: install uninstall installcheck check

all: install-dep dockerbuild 

dockerbuild:
	docker build -t ${OWNER}/${IMAGE}:${TAG} $(ARGS) .

dockerclean:
	docker rmi -f ${OWNER}/${IMAGE}:${TAG}

dockerpush:
	docker push ${OWNER}/${IMAGE}:${TAG}

clean:
	$(MAKE) dockerclean
	$(MAKE) distclean
	rm -fr .pytest_cache
	rm -fr tests/__pycache__

dist:
ifeq ($(wildcard $(${PYTHON})),)
	@echo "Using the virtuale environment Python in ${PYTHON};"
	${PYTHON} setup.py sdist bdist_wheel
else
	python3 setup.py sdist bdist_wheel
endif

distclean:
	rm -fr dist build ${PACKAGE_NAME}.egg-info

maintainer-clean:
	@echo 'This command is intended for maintainers to use; it'
	@echo 'deletes files that may need special tools to rebuild.'
	$(MAKE) distclean

install-dep:
ifeq ($(wildcard $(${ACTIVATE_FILE})),)
	@echo "Using python virtual environment in directory ${VENV_NAME};"
	. ${ACTIVATE_FILE}; pip3 install -r requirements.txt
else
	pip3 install -r requirements.txt
endif

install:
	$(MAKE) install-dep
ifeq ($(wildcard $(${ACTIVATE_FILE})),)
	@echo "Using python virtual environment in directory ${VENV_NAME};"
	. ${ACTIVATE_FILE}; pip3 install .
else
	pip3 install .
endif

uninstall:
ifeq ($(wildcard $(${ACTIVATE_FILE})),)
	@echo "Using python virtual environment in directory ${VENV_NAME};"
	. ${ACTIVATE_FILE}; pip3 uninstall -y -r requirements.txt
	. ${ACTIVATE_FILE}; pip3 uninstall -y ${PACKAGE_NAME}
else
	pip3 uninstall -y -r requirements.txt
endif

installcheck:
ifeq ($(wildcard $(${ACTIVATE_FILE})),)
	@echo "Using python virtual environment in directory ${VENV_NAME};"
	. ${ACTIVATE_FILE}; pip3 install -r tests/requirements.txt
else
	pip3 install -r tests/requirements.txt
endif

# The tests requires access to the docker socket
check:
ifeq ($(wildcard $(${ACTIVATE_FILE})),)
	@echo "Using python virtual environment in directory ${VENV_NAME};"
	. ${ACTIVATE_FILE}; pytest -s -v tests/
else
	pytest -s -v tests/
endif
