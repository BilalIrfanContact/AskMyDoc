"""Remove expired unfinished uploads. Dry-run unless --apply is explicitly provided."""
import argparse

from backend.bootstrap import initialize_backend_environment
from backend.services.demo_limits import UPLOAD_BUCKET
from backend.services.persistence.common import get_postgrest_client
from backend.services.persistence.storage_repository import delete_storage_object


def cleanup_uploads(*, apply: bool = False) -> int:
    client = get_postgrest_client()
    rows = client.rpc('demo_expired_uploads', {}).execute().data
    cleaned = 0
    for row in rows:
        extension = '.pdf' if row['payload']['content_type'] == 'application/pdf' else '.md'
        path = f"{UPLOAD_BUCKET}/{row['user_id']}/{row['id']}/document{extension}"
        if apply:
            delete_storage_object(path)
            client.from_('demo_operations').update({'storage_cleaned': True}).eq('id', row['id']).execute()
        cleaned += 1
    return cleaned


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    initialize_backend_environment()
    count = cleanup_uploads(apply=args.apply)
    print(f'{count} expired upload(s) {"removed" if args.apply else "eligible for cleanup; no changes made"}.')
