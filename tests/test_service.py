import docker
import requests


def test_creates_service(hub_service):
    """Test that logging in as a new user creates a new docker service."""
    client = docker.from_env()
    # jupyterhub service should be running at this point
    services_before_login = client.services.list()

    # login
    session = requests.session()
    login_response = session.post(
        "http://127.0.0.1:8000/hub/login?next=",
        data={"username": "a-new-user",
              "password": "just magnets"})
    assert login_response.status_code == 200
    # Spawn a new service
    spawn_response = session.post("http://127.0.0.1:8000/hub/spawn")
    assert spawn_response.status_code == 200

    services_after_login = client.services.list()
    assert len(services_after_login) - len(services_before_login) == 1

    # Remove the service we just created, or we'll get errors when tearing down the fixtures
    (set(services_after_login) - set(services_before_login)).pop().remove()


def test_create_mig_service(mig_service):
    """ Test that spawning a mig service works"""
    client = docker.from_env()
    services_before_login = client.services.list()
    session = requests.session()
    # Spawn before login -> foot in face
    spawn_resp = session.post("http://127.0.0.1:8000/hub/spawn")
    assert spawn_resp.status_code == 403

    user_cert = '/C=DK/ST=NA/L=NA/O=NBI/OU=NA/CN=Rasmus ' \
                'Munk/emailAddress=rasmus.munk@nbi.ku.dk'
    # Auth header
    auth_header = {'Remote-User': user_cert}
    # login
    login_resp = session.get(
        "http://127.0.0.1:8000/hub/login", headers=auth_header
    )
    assert login_resp.status_code == 200
    # Spawn a MiG mount container without having provided the MiG Mount header
    spawn_no_mig_resp = session.post("http://127.0.0.1:8000/hub/spawn")
    assert 'missing MiG mount authentication keys, try reinitializing them ' \
           'through the MiG interface' in spawn_no_mig_resp.text
    assert (len(client.services.list()) - len(services_before_login)) == 0

    # Provide Valid Mig Mount
    correct_mig_dict = {'SESSIONID': 'randomstring_unique_string',
                        'USER_CERT': user_cert,
                        'TARGET_MOUNT_ADDR': '@host.localhost:',
                        'MOUNTSSHPRIVATEKEY': '''-----BEGIN RSA PRIVATE KEY-----
    MIIEpAIBAAKCAQEA00VP99Nbg6AFrfeByzHtC4G2eLZGDCXP0pBG5tNNmaXKq5sU
    IrDPA7fJczwIfMNlqWeoYjEYg46vbMRxwIDXDDA990JK49+CrpwppxWgSE01WPis
    gtqfmaV16z8CS4WmkjSZnUKQf+2Yk9zdBXOOjWLiXBog7dGpUZQUV/j3u262DIl5
    oLGtoy/mljPx3rwGTSqVoavUW2zh7k0tFIhGt/T14E3TuATdUIDAsPmfLVXFFx76
    W0JxYv3uoCGAUOd2pFhqUXDPLYsSG5reWoQ8iXHJS84E8wHAImcLhYccRLg2AT3b
    TXmC1/BX3lfrwXjaBLfMZiUk/cdSLUh6hxtSPQIDAQABAoIBAQDP4SKHYmNohzsv
    axs+OXjZ2p8V9ZvE9iugLzBkjUOMzHI4GlZcsAZxzRQeG9LqGEVew80OGOra/7mi
    10RqOxveNVWzhnoz78ghUS0253OX0MiOK9lqw/1IbGMzvwLeFrrIn5MLBuUxyzJX
    Q3oClCqO+d5q65a9CpCE4aSGz0XLGKGe9iD5Rd1UjVJn/KvZnjObd0WJBAQCoNVU
    VCULblmR/1c+2lL/0Snv3j7w7G6+2H6o1MI3dbBQ0/SCGjw5cJOXYuGZq9YRXfnj
    3WxQW04j39gOtvZqJfCXK8lh+GE2BqgVG/ei9VGV27FshTM/3AkPACvzFZXTnjoP
    2uc5k8fBAoGBAO59ZzJyRYN+qOIRmM4e3ApZCfpUCaxMsksSDvvIVcJHENu4WcA3
    vPBVsnyDmgn5ZpEwXuoYhnMoDIQobob81jiVARG9RRS+4Kd71E2jOr5UBXFDD05R
    yvxh2deZ9T3hNWIE31T/37d3xLGdnkxQ+nqAyNjYAG7IemqxR877kw7tAoGBAOLI
    Tj7Aaa9cBzjmWVfJOExMT8PpDrGg4MGYh7nQFJB37A6SMrC1jXe6ZqwQtouOC+pG
    Jk310lMjAeC3Gokr769CHE40BY347wcMIBQHnKUW3elZx2APswETMyKYsNllnJWe
    j1f7gc5ZMr8bjWMPjRgIbazdrLCM3lv3ITMDNZaRAoGAXi13SxyFBuBFoMCCLyNQ
    kWWH4yq8hyXiYnLHJ/Z8pzOZHKs4Bgf8vIua6ECv27B5KGyJjrgQn/j4uFefDf9a
    OQ3eVjr/xKl73aewttf2oqJbY9avfKYgGnoppFJP3hfJFOQHrXE9zx2ktt8fW9O+
    lhG1PqxNv3G7pdZMHRiLgiECgYEAgyCazYHoGfM2YdofMrkwij1dqcOqMV76VjZh
    1DjSiy4sGcjC8pYndGEdWMRZKJw7m3xwTYej01pcjZiSCVqUPlwVjcpao9qaKxMB
    wVMdaf+s1G6K76pkMGzvlkN/jlRIk+KYs6DDT5MX2pSNzgeB57GH6PpMDdGGCNr+
    IUbrx2ECgYAck/GKM9grs2QSDmiQr3JNz1aUS0koIrE/jz4rYk/hIG4x7YFoPG4L
    D8rT/LeoFbxDarVRGkgu1pz13IQN2ItBp1qQVr4FqbN4emgj73wOWiFgrlRvasYV
    ojR4eIsIc//+fVpkr56fg2OUGhmI+jw87k9hG5uxgBCqOAJuWjEo7A==
    -----END RSA PRIVATE KEY-----''',
                        'MOUNTSSHPUBLICKEY': 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQ'
                                             'ABAAABAQDTRU/301uDoAWt94HLMe0L'
                                             'gbZ4tkYMJc/SkEbm002ZpcqrmxQisM'
                                             '8Dt8lzPAh8w2WpZ6hiMRiDjq9sxHHA'
                                             'gNcMMD33Qkrj34KunCmnFaBITTVY+K'
                                             'yC2p+ZpXXrPwJLhaaSNJmdQpB/7ZiT'
                                             '3N0Fc46NYuJcGiDt0alRlBRX+Pe7br'
                                             'YMiXmgsa2jL+aWM/HevAZNKpWhq9Rb'
                                             'bOHuTS0UiEa39PXgTdO4BN1QgMCw+Z'
                                             '8tVcUXHvpbQnFi/e6gIYBQ53akWGpR'
                                             'cM8tixIbmt5ahDyJcclLzgTzAcAiZw'
                                             'uFhxxEuDYBPdtNeYLX8FfeV+vBeNoE'
                                             't8xmJST9x1ItSHqHG1I9'}
    correct_mig_header = {
        'Mig-Mount': str(correct_mig_dict)
    }

    # Valid mount header
    auth_mount_response = session.get("http://127.0.0.1:8000/hub/mount",
                                      headers=correct_mig_header)
    assert auth_mount_response.status_code == 200
    spawn_resp = session.post("http://127.0.0.1:8000/hub/spawn")
    assert spawn_resp.status_code == 200

