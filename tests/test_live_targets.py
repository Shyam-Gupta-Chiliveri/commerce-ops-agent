from opsagent.settings import Settings, klaviyo_base, origins, sage_base, shopify_base, zendesk_base


def test_empty_accounts_stay_on_the_sample():
    settings = Settings()
    assert shopify_base(settings) == "http://mock"
    assert zendesk_base(settings) == "http://mock"
    assert klaviyo_base(settings) == "http://mock"
    assert sage_base(settings) == "http://mock"
    assert "local sample" in origins(settings)["en"]


def test_oauth_client_points_at_the_zendesk_account():
    settings = Settings(
        zendesk_subdomain="aisolutions-43207",
        zendesk_client_id="harbor",
        zendesk_client_secret="secret",
    )
    assert zendesk_base(settings) == "https://aisolutions-43207.zendesk.com"


def test_a_real_shop_and_app_are_live():
    settings = Settings(shopify_shop="harbor-demo", shopify_client_id="id", shopify_client_secret="secret")
    assert shopify_base(settings) == "https://harbor-demo.myshopify.com"
    text = origins(settings)["en"]
    assert "https://harbor-demo.myshopify.com" in text
    assert "Zendesk" not in text
