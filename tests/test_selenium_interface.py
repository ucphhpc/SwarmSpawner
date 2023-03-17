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
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager

# Logger
logging.basicConfig(level=logging.DEBUG)
test_logger = logging.getLogger()


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_interface_open(image, swarm, network, make_service):
    driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()))
    test_logger.info("Start of testing that the interface loads")
    make_service(hub_service)
    assert wait_for_site(JHUB_URL) is True
    driver.get(JHUB_URL)
    jupyterhub_logo = driver.find_element(By.ID, "jupyterhub-logo")
    assert jupyterhub_logo.id != ""
    # Authenticate
    driver.close()


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_interface_authenticate(image, swarm, network, make_service):
    driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()))
    test_logger.info("Start of testing that the interface loads")
    make_service(hub_service)
    assert wait_for_site(JHUB_URL) is True
    driver.get(JHUB_URL)
    jupyterhub_logo = driver.find_element(By.ID, "jupyterhub-logo")
    assert jupyterhub_logo.id != ""

    # Fill in credentials
    username_input = driver.find_element(By.ID, "username_input")
    password_input = driver.find_element(By.ID, "password_input")
    username_input.send_keys("user1")
    password_input.send_keys("just magnets")

    # Submit the form
    driver.find_element(By.ID, "login_submit").click()
    spawn_form = driver.find_element(By.ID, "spawn_form")
    assert spawn_form
    # Logout
    driver.find_element(By.ID, "logout").click()
    login_form = driver.find_element(By.ID, "login-main")
    assert login_form
    # Check that we are at the login form again
    driver.close()


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_interface_start_stop(image, swarm, network, make_service):
    driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()))
    test_logger.info("Start of testing that the interface loads")
    make_service(hub_service)
    assert wait_for_site(JHUB_URL) is True
    driver.get(JHUB_URL)
    jupyterhub_logo = driver.find_element(By.ID, "jupyterhub-logo")
    assert jupyterhub_logo.id != ""

    # Fill in credentials
    username_input = driver.find_element(By.ID, "username_input")
    password_input = driver.find_element(By.ID, "password_input")
    username_input.send_keys("user1")
    password_input.send_keys("just magnets")

    # Submit the form
    driver.find_element(By.ID, "login_submit").click()
    spawn_form = driver.find_element(By.ID, "spawn_form")
    assert spawn_form

    # Spawn the Notebook
    driver.find_element(By.CLASS_NAME, "btn.btn-jupyter.form-control").click()

    # wait for the spawn to finish (progress)
    loading = True
    progress_bar = driver.find_element(By.CLASS_NAME, "progress")
    while loading:
        try:
            progress_bar = driver.find_element(By.CLASS_NAME, "progress")
        except NoSuchElementException:
            loading = False

    # Wait for the jupyterhub splash animation has finished
    # Look for the top panel bar
    splashed = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "jp-top-panel"))
    )
    assert splashed

    # TODO, Jump back to the JupyterHub page and shutdown the instance
    # file_btn = driver.find_element(By.CLASS_NAME, "lm-MenuBar-itemLabel p-MenuBar-itemLabel")
    driver.close()


# @pytest.mark.parametrize("image", [hub_image], indirect=["image"])
# @pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
# @pytest.mark.parametrize("network", [network_config], indirect=["network"])
# def test_multiple_users_interface_start_stop(image, swarm, network, make_service):
#     driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()))
#     test_logger.info("Start of testing that the interface loads")
#     make_service(hub_service)
#     assert wait_for_site(JHUB_URL) is True
#     jupyterhub_page =driver.get(JHUB_URL)
#     # Retrieve the site

#     # Push the start button

#     # test the progress page

#     # redirect to the hub page

#     # stop the server

#     driver.close()
