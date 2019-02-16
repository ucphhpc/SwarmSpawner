import requests

JHUB_URL = 'http://127.0.0.1'
IMAGE_NAME = 'nielsbohr/slurm-notebook:edge'

if __name__ == "__main__":
    # Make spawn request
    with requests.Session() as session:
        result = session.get(JHUB_URL)
        # Get login page
        login_url = JHUB_URL + "/hub/login"
        page_resp = session.get(login_url)
        if page_resp.status_code != 200:
            print("Failed to GET the {} URL".format(page_resp))
            exit(1)
        # Login as test user
        user = 'test_user'
        login_resp = session.post(JHUB_URL + "/hub/login?next=",
                                  data={"username": user,
                                        "password": "password"})
        if login_resp.status_code != 200 and login_resp.status_code != 302 \
                and login_resp.status_code != 500:
            print("Failed to login to {} as {}".format(JHUB_URL, user))
            exit(1)

        payload = {'dockerimage': IMAGE_NAME}
        # Spawn a notebook with image name
        spawn_resp = session.post(JHUB_URL + "/hub/spawn",
                                  data=payload)
        if spawn_resp.status_code != 200 and spawn_resp.status_code != 302:
            print("Failed to spawn notebook {} at {}".format(
                payload['dockerimage'], JHUB_URL))
            exit(1)
