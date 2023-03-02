import logging
import pytest
from tests.defaults import (
    hub_image,
    swarm_config,
    network_config,
    hub_service,
    JHUB_URL,
)
from tests.util import wait_for_site
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager

#driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()))

# Logger
logging.basicConfig(level=logging.INFO)
test_logger = logging.getLogger()

@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_interface_open(image, swarm, network, make_service):
    test_logger.info("Start of testing that the interface loads")
    make_service(hub_service)
    assert wait_for_site(JHUB_URL) is True
