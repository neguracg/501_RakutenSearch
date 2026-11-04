"""Prompt locally for credentials and run exactly one API request."""
import getpass
import os
import sys
import warnings
import preflight


def main():
    names = ('RAKUTEN_APPLICATION_ID', 'RAKUTEN_ACCESS_KEY')
    previous = {name: os.environ.get(name) for name in names}
    try:
        # Refuse a terminal that cannot hide input instead of echoing credentials.
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            app_id = getpass.getpass('Application ID (hidden): ').strip()
            access_key = getpass.getpass('Access Key (hidden): ').strip()
        os.environ[names[0]] = app_id
        os.environ[names[1]] = access_key
        return preflight.main(['--live'])
    except (getpass.GetPassWarning, EOFError):
        print('Hidden input unavailable. Run in a local interactive PowerShell window.')
        return 1
    except KeyboardInterrupt:
        print('\nCancelled.')
        return 1
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == '__main__':
    sys.exit(main())
