SHELL:=/bin/bash
PACKAGE_NAME=jhub-swarmspawner
PACKAGE_NAME_FORMATTED=$(subst -,_,$(PACKAGE_NAME))
OWNER=ucphhpc
IMAGE=$(PACKAGE_NAME)
# Enable that the builder should use buildkit
# https://docs.docker.com/develop/develop-images/build_enhancements/
DOCKER_BUILDKIT=1
# NOTE: dynamic lookup with docker as default and fallback to podman
DOCKER = $(shell which docker 2>/dev/null || which podman 2>/dev/null)
TAG=edge
ARGS=

MOUNT_PLUGIN := $(shell ${DOCKER} plugin inspect ucphhpc/sshfs:latest > /dev/null 2>&1  && echo 0 || echo 1)

.PHONY: all
all: venv install-dep init dockerbuild

.PHONY: init
init:
ifeq ($(shell test -e defaults.env && echo yes), yes)
ifneq ($(shell test -e .env && echo yes), yes)
		ln -s defaults.env .env
endif
endif

.PHONY: dockerbuild
dockerbuild:
	${DOCKER} build -t ${OWNER}/${IMAGE}:${TAG} .

.PHONY: dockerclean
dockerclean:
	${DOCKER} rmi -f ${OWNER}/${IMAGE}:${TAG}

.PHONY: dockerpush
dockerpush:
	${DOCKER} push ${OWNER}/${IMAGE}:${TAG}

.PHONY: clean
clean: dockerclean distclean venv-clean
	rm -fr .env
	rm -fr .pytest_cache
	rm -fr tests/__pycache__

.PHONY: dist
dist: venv
	$(VENV)/python setup.py sdist bdist_wheel

.PHONY: distclean
distclean:
	rm -fr dist build $(PACKAGE_NAME).egg-info $(PACKAGE_NAME_FORMATTED).egg-info

.PHONY: maintainer-clean
maintainer-clean:
	@echo 'This command is intended for maintainers to use; it'
	@echo 'deletes files that may need special tools to rebuild.'
	$(MAKE) distclean

.PHONY: install-dev
install-dev: venv
	$(VENV)/pip install -r requirements-dev.txt

.PHONY: uninstall-dev
uninstall-dev: venv
	$(VENV)/pip uninstall -y -r requirements-dev.txt

.PHONY: install-dep
install-dep: venv
	$(VENV)/pip install -r requirements.txt

.PHONY: install
install: install-dep
	$(VENV)/pip install .

.PHONY: uninstall
uninstall: venv
	$(VENV)/pip uninstall -y -r requirements.txt
	$(VENV)/pip uninstall -y -r $(PACKAGE_NAME)

.PHONY: uninstalltest
uninstalltest: venv
	$(VENV)/pip uninstall -y -r tests/requirements.txt
	@echo
	@echo "*** WARNING ***"
	@echo "*** Deleting every ucphhpc/sshfs:latest volume in 10 seconds ***"
	@echo "*** Hit Ctrl-C to abort to preserve any local user and cert data ***"
	@echo
	@sleep 10
	if [ "$$(docker volume ls -q -f 'driver=ucphhpc/sshfs:latest')" != "" ]; then\
		docker volume rm -f $$(docker volume ls -q -f 'driver=ucphhpc/sshfs:latest');\
	fi
	docker plugin disable ucphhpc/sshfs:latest
	docker plugin rm ucphhpc/sshfs:latest

.PHONY: installtest
installtest: venv
	$(VENV)/pip install -r tests/requirements.txt
	@echo "Checking for the required ucphhpc/sshfs docker plugin for testing"
ifeq ($(MOUNT_PLUGIN), 1)
	@echo "The ucphhpc/sshfs docker plugin was not found"
	@echo "Installing the missing ucphhpc/sshfs docker plugin"
	@docker plugin install ucphhpc/sshfs:latest --grant-all-permissions
else
	@echo "Found the ucphhpc/sshfs docker plugin"
endif

# The tests requires access to the docker socket
.PHONY: test
test: installtest
	. $(VENV)/activate; python3 setup.py check -rms
	. $(VENV)/activate; pytest -s -v tests/

include Makefile.venv
