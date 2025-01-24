from http import HTTPStatus

import flask.testing


def test_userinfo_unauthorized(client: flask.testing.FlaskClient):
    response = client.get("/userinfo")
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.www_authenticate.type == "bearer"
    assert response.json
    assert response.json["error"] == "missing_authorization"

    response = client.get("/userinfo", headers={"authorization": "foo"})
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json == {"error": "unsupported_token_type"}

    response = client.get("/userinfo", headers={"authorization": "Bearer foo"})
    # TODO: should be unauthorized
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json
    assert response.json["error"] == "access_denied"
