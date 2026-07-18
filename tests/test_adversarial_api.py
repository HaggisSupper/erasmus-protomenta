from urllib.request import urlopen
from erasmus.adversarial_api import AdversarialApi

def test_adversarial_api_scenarios():
    api = AdversarialApi("malformed"); url = api.start()
    try:
        assert urlopen(url).read() == b"not-json"
    finally: api.stop()
