PACKAGE_NAME=jhub-swarmspawner
PACKAGE_NAME_FORMATTED=$(subst -,_,$(PACKAGE_NAME))
OWNER=ucphhpc
IMAGE=$(PACKAGE_NAME)
TAG=edge
ARGS=

MOUNT_PLUGIN := $(shell docker plugin inspect ucphhpc/sshfs:latest > /dev/null 2>&1  && echo 0 || echo 1)

.PHONY: all init dockerbuild dockerclean dockerpush clean dist distclean maintainer-clean
.PHONY: install uninstall installcheck check

all: venv install-dep init dockerbuild

init:
ifeq ($(shell test -e defaults.env && echo yes), yes)
ifneq ($(shell test -e .env && echo yes), yes)
		ln -s defaults.env .env
endif
endif

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
	rm -fr .env
	rm -fr .pytest_cache
	rm -fr tests/__pycache__

dist:
	$(VENV)/python setup.py sdist bdist_wheel

distclean:
	rm -fr dist build $(PACKAGE_NAME).egg-info $(PACKAGE_NAME_FORMATTED).egg-info

maintainer-clean:
	@echo 'This command is intended for maintainers to use; it'
	@echo 'deletes files that may need special tools to rebuild.'
	$(MAKE) distclean

install-dev:
	$(VENV)/pip install -r requirements-dev.txt

uninstall-dev:
	$(VENV)/pip uninstall -y -r requirements-dev.txt

install-dep:
	$(VENV)/pip install -r requirements.txt

install:
	$(MAKE) install-dep
	$(VENV)/pip install .

uninstall:
	$(VENV)/pip uninstall -y -r requirements.txt
	$(VENV)/pip uninstall -y -r $(PACKAGE_NAME)

uninstallcheck:
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

installcheck:
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
check:
	. $(VENV)/activate; python3 setup.py check -rms
	. $(VENV)/activate; pytest -s -v tests/

include Makefile.venv
