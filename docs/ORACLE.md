# Ground oracle (behavior baseline)

The test suite is a frozen, reproducible record of how the app behaves **today**, before any
feature work or dependency upgrades. It encodes current behavior exactly, including 500s and
quirks. Treat a failing oracle test as "behavior changed": find out why before you change the test.

## Running it

The pinned environment is Python **3.7.17** (`runtime.txt`, `Pipfile`, CI image).

```sh
pip install -r requirements/dev.txt
export FLASK_APP=autoapp.py
flask test   # pytest over tests/
flask lint   # flake8 (setup.cfg: max-line-length=120)
```

To match CI exactly, use the same container image:

```sh
docker run --rm -v "$PWD":/src -w /src -e FLASK_APP=autoapp.py \
  python:3.7.17-bookworm@sha256:eedf63967cdb57d8214db38ce21f105003ed4e4d0358f02bedc057341bcf92a0 \
  sh -c 'pip install -r requirements/dev.txt && flask test && flask lint'
```

CI (`.github/workflows/ci.yml`) is the only CI config and the gate that protects the oracle.
It runs in that image with `FLASK_DEBUG=0` and `FLASK_DEBUG=1`. It checks that `pip freeze`
matches the pins exactly, then runs `flask test` and `flask lint`. Any failure fails the build.
The legacy `.travis.yml` (2.7–3.6) and `.circleci/config.yml` (3.6.0) were removed so there is
only one Python version.

## What is frozen

### Environment

* `requirements/prod.txt` and `requirements/dev.txt` are the source of truth. Every package,
  transitive ones included, is pinned to `==`, and the `-r` include structure is unchanged. The
  `Pipfile` mirrors the direct pins. The old `Pipfile.lock` was removed: it locked a different,
  older set (Flask 1.0.2, marshmallow 2) that no longer matched the code.
* The pins come from a clean install of the previously unpinned requirements on 3.7.17, plus the
  smallest set of constraints needed for the app to import at all. Today an unpinned install
  resolves Flask 2.2 / Flask-JWT-Extended 4, and the app then crashes on import:

  | Pin | Why |
  | --- | --- |
  | `SQLAlchemy==1.1.9`, `Flask_SQLAlchemy==2.2` | pre-existing pins, kept |
  | `Flask==1.1.4` (+ `Werkzeug==1.0.1`, `Jinja2==2.11.3`, `itsdangerous==1.1.0`, `click==7.1.2`) | Flask_SQLAlchemy 2.2 uses `_app_ctx_stack.__ident_func__`, removed in Werkzeug 2.1 / Flask 2.2 |
  | `Flask-JWT-Extended==3.25.1` (+ `PyJWT==1.7.1`) | the code uses `jwt_optional` / `user_loader_callback_loader`, removed in 4.0 |
  | `MarkupSafe==2.0.1` | Jinja2 2.11 imports `soft_unicode`, removed in MarkupSafe 2.1 |
  | `importlib-metadata==4.2.0` | `flake8==5.0.4` on Python 3.7 needs `<4.3` |
  | `flake8==5.0.4` | added so `flask lint` can run; last release supporting 3.7 |

  Everything else is the version the clean install resolved.

### Test configuration

* `TestConfig` (`conduit/settings.py`) has a fixed `SECRET_KEY` and
  `JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)`, so token claims can be asserted. The
  `Config`/`ProdConfig` defaults, including the hardcoded `'secret-key'` fallback, are deliberately
  **unchanged**. That fallback is a known issue for the upgrade.
* Tests always run under `TestConfig` (in-memory SQLite) through the `app` fixture, whatever
  `FLASK_DEBUG` is set to. `tests/test_config.py` asserts this.

### Behavior

* `tests/test_oracle_*.py` contain characterization tests for every endpoint: status codes, JSON
  envelopes (`user`, `profile`, `article`, `articles`/`articlesCount`, `comments`, `tags`), key
  fields, error shapes, JWT rejection paths and serializer edge cases.
* Golden masters under `tests/golden/` (`tests/test_oracle_golden.py`):
  * `url_map.txt`: every route with its endpoint, methods and arguments (the same data as
    `flask urls`). It catches routes being added, removed or changed.
  * `responses/*.json`: status, content type and normalized body for representative requests.
    `token`, `createdAt` and `updatedAt` are replaced with `<token>` / `<timestamp>`.

## Known bugs encoded on purpose

Each of these tests is marked `@pytest.mark.oracle_known_bug` and has the comment
`# ORACLE: encodes current (buggy) behavior — revisit after upgrade`. To list them:

```sh
pytest -m oracle_known_bug --collect-only -q
```

| Test | Current behavior |
| --- | --- |
| `test_oracle_articles.py::TestDeleteArticle::test_missing_slug_raises_attribute_error` / `test_missing_slug_is_500` | `DELETE /api/articles/<missing>` hits `None.delete()`: `AttributeError` (500) instead of 404 |
| `TestDeleteArticle::test_non_owner_is_500_and_article_survives` | non-owner delete gives 500 instead of 403/404 |
| `TestComments::test_delete_missing_comment_raises_attribute_error` / `test_delete_missing_comment_is_500` | deleting a missing comment gives `AttributeError` (500) |
| `TestComments::test_delete_other_users_comment_is_500` | deleting another user's comment gives 500 (`COMMENT_NOT_OWNED` is never used) |
| `TestListArticles::test_query_string_filters_are_ignored` | `tag`/`author`/`favorited`/`limit`/`offset` query params are ignored. flask-apispec 0.11 + webargs 8 `use_kwargs` reads only the JSON body, even on GET (the same applies to the feed's `limit`/`offset`) |
| `TestListArticles::test_by_favorited_ignores_who_favorited` | the `favorited` filter cross-joins `users`, so any existing username returns every favorited article |
| `TestListArticles::test_author_and_favorited_together_raise` / `_is_500` | combining `author` + `favorited` gives `OperationalError: ambiguous column name` (500) |
| `TestFavorite::test_favorited_state_leaks_across_articles` | `is_favourite`/`favorited` check "favorited any article": `favorited` is true on articles you never favorited, and favoriting a second article is silently skipped |
| `TestGetArticle::test_identity_leaks_to_later_anonymous_requests_in_test_app` | test harness: Flask-JWT-Extended 3 caches the user on the app context, which the `app` fixture keeps pushed, so later anonymous requests in the same test still see the last user |
| `test_oracle_user.py::TestLoginFailures::test_wrong_password_is_404_user_not_found` | a wrong password returns 404 `User not found`, not 401/422 |
| `TestGetUser::test_echoes_token_parsed_from_raw_header` | `get_user` echoes the token parsed from `HTTP_AUTHORIZATION` with `split('Token ')[1]` |

Other quirks are asserted without the marker: the slug is not regenerated when the title changes,
`articlesCount` is the page size rather than the total, `DELETE` endpoints return an empty
`text/html` 200, JWT errors use `{"msg": ...}` instead of the `errors` envelope, and unknown routes
or methods return Werkzeug HTML pages.

## Comparing after an upgrade

1. On the baseline (this commit, pinned env), confirm that `flask test` and `flask lint` are green.
2. Make **one** change at a time (dependency bump, Python bump, feature, `SECRET_KEY` fix).
3. Rerun `flask test` and `flask lint`.
4. Investigate every diff:
   * An unintended change is a regression. Fix the code, not the oracle.
   * An intended change (for example, fixing an `oracle_known_bug`): update the test, remove its
     marker and the `# ORACLE:` comment, and update the table above in the same PR.
   * For golden files, re-record with `ORACLE_UPDATE_GOLDEN=1 flask test` and review
     `git diff tests/golden/` line by line before committing.
5. When re-pinning, regenerate the pins from `pip freeze` in a clean environment, and keep CI's
   freeze check green.
