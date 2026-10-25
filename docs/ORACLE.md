# Ground oracle (behavior baseline)

The test suite is a frozen, reproducible record of how the app behaves **today**, before any
feature work or dependency upgrades. It encodes current behavior exactly, including 500s and
quirks. Treat a failing oracle test as "behavior changed": find out why before you change the test.

## Running it

The pinned environment is Python **3.13.17** (`runtime.txt`, `Pipfile`, CI image).

```sh
pip install -r requirements/dev.txt
export FLASK_APP=autoapp.py
flask test   # pytest over tests/
flask lint   # flake8 (setup.cfg: max-line-length=120)
```

To match CI exactly, use the same container image:

```sh
docker run --rm -v "$PWD":/src -w /src -e FLASK_APP=autoapp.py \
  python:3.13.17-bookworm@sha256:a3799099b64fd333f262768c7a64733f6e4edb7bc569813710a100214bdcf278 \
  sh -c 'pip install -r requirements/dev.txt && flask test && flask lint'
```

CI (`.github/workflows/ci.yml`) is the only CI config and the gate that protects the oracle.
It runs in that image with `FLASK_DEBUG=0` and `FLASK_DEBUG=1`. It checks that `pip freeze`
matches the pins exactly, then runs `flask test` and `flask lint`. Any failure fails the build.
The legacy `.travis.yml` (2.7–3.6) and `.circleci/config.yml` (3.6.0) were removed so there is
only one Python version.

### Merge gate (branch protection)

Passing CI is required to merge into the default branch (`dependabot/pip/mako-1.2.2`). This is a
GitHub repository setting, not a committed file, so a repo admin has to apply it. The rule:

* requires a pull request before merging (no approvals required);
* requires status checks to pass, with "require branches to be up to date" (`strict`) enabled;
* requires both matrix jobs of the `CI` workflow, by their exact check names:
  * `Oracle (Python 3.13.17, FLASK_DEBUG=0)`
  * `Oracle (Python 3.13.17, FLASK_DEBUG=1)`
* binds them to the GitHub Actions app (`app_id` 15368), so only Actions can satisfy them;
* applies to admins too (`enforce_admins`).

Apply it as an admin (the branch name contains `/`, so it is URL-encoded):

```sh
gh api --method PUT \
  -H "Accept: application/vnd.github+json" \
  "repos/acme-financial-sandbox/conduit-api/branches/dependabot%2Fpip%2Fmako-1.2.2/protection" \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {"context": "Oracle (Python 3.13.17, FLASK_DEBUG=0)", "app_id": 15368},
      {"context": "Oracle (Python 3.13.17, FLASK_DEBUG=1)", "app_id": 15368}
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0
  },
  "restrictions": null
}
JSON
```

Check it:

```sh
gh api "repos/acme-financial-sandbox/conduit-api/branches/dependabot%2Fpip%2Fmako-1.2.2/protection" \
  --jq '{strict: .required_status_checks.strict, checks: [.required_status_checks.checks[].context], pr: (.required_pull_request_reviews != null), admins: .enforce_admins.enabled}'
```

If the job `name:` or the matrix in `ci.yml` changes, update the required check names too.
Otherwise every PR waits forever on a check that never reports.

## What is frozen

### Environment

* `requirements/prod.txt` and `requirements/dev.txt` are the source of truth. Every package,
  transitive ones included, is pinned to `==`, and the `-r` include structure is unchanged. The
  `Pipfile` mirrors the direct pins. The old `Pipfile.lock` was removed: it locked a different,
  older set (Flask 1.0.2, marshmallow 2) that no longer matched the code.
* The pins come from a clean install of the previously unpinned requirements on 3.7.17, plus the
  smallest set of constraints needed for the app to import at all. Upgrade step 2 moved to 3.13.17:
  the direct pins were kept and the transitive ones re-resolved by a clean install on 3.13.17, except
  for the holds marked "held" below. On 3.7.17 an unpinned install
  resolved Flask 2.2 / Flask-JWT-Extended 4, and the app then crashed on import:

  | Pin | Why |
  | --- | --- |
  | `SQLAlchemy==2.0.55`, `Flask_SQLAlchemy==3.1.1` | upgrade step 5 (step 1 went 1.1.9 → 1.4: `db.Binary` became `db.LargeBinary` with the same DDL, and `postgres://` URLs are rewritten to `postgresql://`). Kept on 2.0 because 2.1 makes `postgresql://` default to psycopg 3 instead of psycopg2. The feed joins an explicit `follows.subquery()` (2.0 can't join a dynamic relationship), and `SurrogatePK.id` uses `sort_order=-1` so `id` stays the first column. 2.0 no longer cascades through backrefs, so new objects added via a relationship log a `not in session` SAWarning until `save()` adds them; the state that ends up committed is the same |
  | `Flask==3.1.3` (+ `Werkzeug==3.1.9`, `Jinja2==3.1.6`, `itsdangerous==2.2.0`, `click==8.5.0`, `blinker==1.9.0`, `Flask-Cors==6.0.5`) | upgrade step 4. `conduit/http_compat.py` keeps the Flask 1.1 `jsonify` bytes and the Werkzeug 1.0 HTML error pages; the blueprint CORS hook is attached once (Flask ≥2.2 forbids changing a registered blueprint) and looks up each app's options per request |
  | `Flask-JWT-Extended==4.3.1` (+ `PyJWT==2.15.1`) | upgrade step 3: last 4.x release that supports Flask 1. `JWT_IDENTITY_CLAIM = 'identity'` keeps the 3.x token layout (old tokens stay valid), and `conduit/jwt_compat.py` ports the 3.25.1 header parsing, token-type check and `jwt_optional` so responses are unchanged |
  | `MarkupSafe==3.0.4`, `Flask-JWT-Extended==4.7.4`, `psycopg2==2.9.13` | pulled into step 4: Flask-JWT-Extended 4.3.1 needs Flask <3 (`JWT_COOKIE_CSRF_PROTECT = False` keeps the csrf claim out of header tokens); `add_models_to_shell=False` keeps the Flask-SQLAlchemy 3 shell context unchanged; Flask-SQLAlchemy 3 (also step 4, because 2.5.1 does not import on Flask 3) creates the engine in `init_app`, so the ProdConfig app now imports psycopg2, and 2.9.9 fails to import on Python 3.13 |
  | `flake8==5.0.4` | added so `flask lint` can run; kept from the 3.7 baseline, dev tools are upgraded in a later step |
  | `bcrypt==4.2.1` (held) | bcrypt 5 raises `ValueError` for passwords over 72 bytes instead of truncating; decided in a later step |
  | `webargs==8.3.0`, `apispec==6.3.1` (held) | upgraded together with marshmallow in a later step |
  | `python-dateutil==2.9.0.post0` (held) | 3.0.0 is a brand-new major release (Faker dependency) |
  | `coverage==7.2.7` (held) | dev tools are upgraded in a later step |
  | `legacy-cgi==2.6.4` | WebOb (WebTest) needs it on Python ≥3.13, where `cgi` was removed |

  Everything else is the version the clean install resolved.

### Test configuration

* `TestConfig` (`conduit/settings.py`) has a fixed `SECRET_KEY` and
  `JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)`, so token claims can be asserted. The
  `Config`/`ProdConfig` defaults, including the hardcoded `'secret-key'` fallback, are deliberately
  **unchanged**. That fallback is a known issue for the upgrade.
* CI also runs the suite under `coverage` (config in `setup.cfg`) and fails below 90% branch
  coverage of `conduit/` (currently ~99%).
* Tests always run under `TestConfig` (in-memory SQLite) through the `app` fixture, whatever
  `FLASK_DEBUG` is set to. `tests/test_config.py` asserts this.

### Behavior

* `tests/test_oracle_*.py` contain characterization tests for every endpoint: status codes, JSON
  envelopes (`user`, `profile`, `article`, `articles`/`articlesCount`, `comments`, `tags`), key
  fields, error shapes, JWT rejection paths and serializer edge cases.
* Golden masters under `tests/golden/` (`tests/test_oracle_golden.py`):
  * `url_map.txt`: every route with its endpoint, methods and arguments (the same data as
    `flask urls`). It catches routes being added, removed or changed.
  * `schema.txt`: every table and column with type, nullability, uniqueness and foreign keys
    (`tests/test_oracle_models.py`). It catches ORM/schema drift during a SQLAlchemy upgrade.
  * `cli_urls.txt`: the exact output of `flask urls` (`tests/test_oracle_commands.py`).
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
| `test_oracle_user.py::TestLoginFailures::test_wrong_password_is_404_user_not_found` | a wrong password returns 404 `User not found`, not 401/422 |
| `TestGetUser::test_echoes_token_parsed_from_raw_header` | `get_user` echoes the token parsed from `HTTP_AUTHORIZATION` with `split('Token ')[1]` |
| `test_oracle_validation.py::TestUnvalidatedInput::*` | missing required fields (`username`/`email`/`password`/`title`/`description`/`body`), missing envelopes (`user`/`article`/`comment`), empty or form-encoded bodies, and unexpected `slug`/`createdAt` on create reach the view and raise `TypeError`/`KeyError` (500) |
| `TestSchemaValidation::test_422_is_html_without_field_errors` | marshmallow validation failures (bad email/URL, unknown field, null field, non-int `limit`) are Werkzeug HTML 422s with no field errors |
| `test_oracle_user_update.py::TestUpdateUser::test_response_token_is_empty` | `PUT /api/user` returns `token: ""` (the `User.token` class default) |
| `TestUpdateUser::test_updated_at_is_not_bumped` / `test_sending_updated_at_resets_it_to_created_at` | `updated_at` never changes on update; sending `updatedAt` sets it to `created_at` |
| `TestUpdateUser::test_duplicate_raises_integrity_error` / `test_duplicate_is_500` | changing email/username to a taken one is an `IntegrityError` (500), not 422 |
| `TestJwtEdges::test_token_without_exp_is_accepted` | a correctly signed token with no `exp` claim never expires |
| `test_oracle_profiles.py::TestGetProfile::test_exposes_email` | public profiles include the user's email |
| `test_oracle_articles_edges.py::TestCreateArticle::test_duplicate_title_*` | a title that slugifies to an existing slug is an `IntegrityError` (500) |
| `TestUpdateArticleEdges::test_body_slug_overrides_url_slug` | a `slug` in the PUT body replaces the URL `<slug>` used for the lookup |
| `TestUpdateArticleEdges::test_created_at_is_client_writable` | `createdAt` can be overwritten on update |
| `TestUpdateArticleEdges::test_tag_list_update_*` | updating `tagList` assigns strings to the relationship: `AttributeError` (500) |
| `TestDeleteArticleEdges::test_article_with_comments_*` | deleting an article that has comments nulls `comment.article_id`: `IntegrityError` (500), article survives |
| `TestCommentEdges::test_id_and_created_at_are_client_writable` | clients can choose the comment `id` and `createdAt` |
| `TestCommentEdges::test_delete_non_numeric_id_raises` / `test_delete_comment_via_other_article_slug_is_500` | non-numeric or other-article comment ids hit `None.delete()` (500) |
| `test_oracle_commands.py::TestUrls::test_matching_url_crashes` | `flask urls --url <matching path>` crashes formatting the arguments dict (`TypeError`) |

Other quirks are asserted without the marker: the slug is not regenerated when the title changes,
`articlesCount` is the page size rather than the total, `DELETE` endpoints return an empty
`text/html` 200, JWT errors use `{"msg": ...}` instead of the `errors` envelope, and unknown routes
or methods return Werkzeug HTML pages. Also: following yourself is a silent 200 no-op, trailing
slashes are accepted, `limit: -1` returns every article, the article list is oldest-first (the feed
is newest-first), slugs/usernames/emails are case-sensitive, and SQLite does not enforce `String(n)`
lengths (PostgreSQL would).

The wire format is pinned in `tests/test_oracle_wire_format.py`, because the other tests compare
parsed JSON and the golden files mask timestamps. JSON bodies use Flask 1.1 `jsonify`: sorted keys,
non-ASCII escaped as `\uXXXX`, and a trailing newline. They are pretty-printed (indent 2, `", "`
separators) when `app.debug` is on (TestConfig/DevConfig) and compact under ProdConfig. Timestamps
are naive `datetime.isoformat()` strings (no offset or `Z`, microseconds dropped when zero), and
a client-supplied UTC offset is discarded rather than converted. A request without an `Origin`
header still gets `Access-Control-Allow-Origin: http://0.0.0.0:4000`, the first whitelist entry in
sorted order.

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
