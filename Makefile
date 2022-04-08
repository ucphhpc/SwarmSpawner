PACKAGE_NAME=jhub-swarmspawner
PACKAGE_NAME_FORMATTED=$(subst -,_,$(PACKAGE_NAME))
OWNER=ucphhpc
IMAGE=$(PACKAGE_NAME)
TAG=edge
ARGS=

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