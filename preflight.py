"""One-request Rakuten API probe. No product data or credentials are printed/saved."""
import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ENDPOINT = 'https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701'


class ProbeError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_request(app_id, access_key, keyword):
    if not app_id or not access_key:
        raise ProbeError('missing_credentials')
    if any(c in app_id + access_key for c in '\r\n'):
        raise ProbeError('invalid_credentials')
    if not keyword.strip() or len(keyword.encode('utf-8')) > 128:
        raise ProbeError('invalid_keyword')
    params = dict(applicationId=app_id, keyword=keyword, format='json',
                  formatVersion=2, hits=1, page=1, availability=0)
    return Request(ENDPOINT + '?' + urlencode(params),
                   headers={'accessKey': access_key, 'Accept': 'application/json'})


def inspect_response(data):
    if not isinstance(data, dict) or 'error' in data:
        raise ProbeError('unexpected_response')
    # Lowercase is documented; uppercase is accepted but recorded, never guessed silently.
    present = [key for key in ('items', 'Items') if key in data]
    if len(present) != 1 or not isinstance(data[present[0]], list):
        raise ProbeError('unexpected_items_structure')
    items = data[present[0]]
    if len(items) > 1:
        raise ProbeError('unexpected_item_count')
    count = data.get('count')
    if type(count) is not int or count < 0:
        raise ProbeError('unexpected_count')
    if (count == 0) != (len(items) == 0):
        raise ProbeError('inconsistent_count')
    missing = set()
    invalid_url = 0
    fields = ('itemCode', 'itemName', 'itemPrice', 'itemUrl', 'postageFlag',
              'shopName', 'availability', 'reviewCount', 'itemCaption')
    for item in items:
        if not isinstance(item, dict) or 'Item' in item or 'item' in item:
            raise ProbeError('unexpected_item_structure')
        missing.update(f for f in fields if f not in item)
        try:
            u = urlsplit(item.get('itemUrl', ''))
            valid = (u.scheme == 'https' and u.hostname == 'item.rakuten.co.jp'
                     and len([p for p in u.path.split('/') if p]) >= 2
                     and not u.username and not u.password)
        except (ValueError, TypeError):
            valid = False
        invalid_url += not valid
    return dict(status='schema_observed' if items else 'empty_result_schema_unverified',
                items_key=present[0], search_count=count, received=len(items),
                missing_fields=sorted(missing), item_url_needs_review=invalid_url)


def probe(req, opener=None):
    opener = opener or build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=20) as response:
            if response.status != 200:
                raise ProbeError('unexpected_http_status')
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProbeError('response_too_large')
        return inspect_response(json.loads(raw))
    except HTTPError as exc:
        # Do not echo the URL, body, headers or exception message (may contain secrets).
        code = exc.code
        exc.close()
        raise ProbeError(f'http_{code}') from None
    except (TimeoutError, socket.timeout):
        raise ProbeError('timeout') from None
    except URLError:
        raise ProbeError('network_error') from None
    except (UnicodeError, json.JSONDecodeError):
        raise ProbeError('invalid_json') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='send exactly one request, no retry')
    parser.add_argument('--keyword', default='ソーラーパネル 500W')
    args = parser.parse_args(argv)
    result = dict(checked_at=datetime.now(timezone(timedelta(hours=9))).isoformat(),
                  python=sys.version.split()[0], live_requested=args.live)
    try:
        app_id = os.environ.get('RAKUTEN_APPLICATION_ID', '')
        access_key = os.environ.get('RAKUTEN_ACCESS_KEY', '')
        result['credentials_present'] = bool(app_id and access_key)
        if args.live:
            result.update(probe(make_request(app_id, access_key, args.keyword)))
        else:
            result['status'] = 'offline_environment_check_only'
        code = 0
    except ProbeError as exc:
        result['status'] = str(exc)
        code = 1
    except Exception:
        result['status'] = 'unexpected_error_details_suppressed'
        code = 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
