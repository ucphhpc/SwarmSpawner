PACKAGE_NAME=jhub_swarmspawner
OWNER=ucphhpc
IMAGE=swarmspawner
TAG=edge
ARGS=

#VENV_NAME=venv
#VENV_DIR=$(VENV_NAME)/bin
#ACTIVATE_FILE=$(VENV_DIR)/activate
#PYTHON=$(VENV_DIR)/python3

.PHONY: dockerbuild dockerclean dockerpush clean dist distclean maintainer-clean
.PHONY: install uninstall installcheck check

all: venv install-dep dockerbuild

dockerbuild:
	docker build -t $(OWNER)/$(IMAGE):$(TAG) $(ARGS) .

dockerclean:
	docker rmi -f $(OWNER)/$(IMAGE):$(TAG)

dockerpush:
	docker push $(OWNER)/$(IMAGE):$(TAG)

clean:
	$(MAKE) dockerclean
	$(MAKE) distclean
	$(MAKE) venv-clean
	rm -fr .pytest_cache
	rm -fr tests/__pycache__

dist:
	$(VENV)/python setup.py sdist bdist_wheel

distclean:
	rm -fr dist build ${PACKAGE_NAME}.egg-info

maintainer-clean:
	@echo 'This command is intended for maintainers to use; it'
	@echo 'deletes files that may need special tools to rebuild.'
	$(MAKE) distclean

install-dep:
	$(VENV)/pip install -r requirements.txt

install:
	$(MAKE) install-dep
	$(VENV)/pip install .

uninstall:
	$(VENV)/pip uninstall -y -r requirements.txt
	$(VENV)/pip uninstall -y -r $(PACKAGE_NAME)

installcheck:
	$(VENV)/pip install -r tests/requirements.txt

# The tests requires access to the docker socket
check:
	. $(VENV)/activate; pytest -s -v tests/

include Makefile.venv