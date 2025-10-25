import os
import requests
import logging
from typing import Optional

FCCC_CHANNEL_ID = 'UC8butISFwT-Wl7EV0hUK0BQ'
YOUTUBE_SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search'
YOUTUBE_PLAYLIST_ITEMS_URL = 'https://www.googleapis.com/youtube/v3/playlistItems'


def _fetch_from_rapidapi(category: Optional[str], max_playlists: int, items_per_playlist: int, rapidapi_key: str, rapidapi_host: str):
    """
    Fetch learning paths (courses) from the RapidAPI 'collection-for-coursera-courses' endpoint.
    This returns a list of "paths" normalized to the same shape as the YouTube-based output.
    """
    url = 'https://collection-for-coursera-courses.p.rapidapi.com/rapidapi/course/get_course.php'
    params = {
        'page_no': 1,
        'course_institution': category or ''
    }
    headers = {
        'x-rapidapi-key': rapidapi_key,
        'x-rapidapi-host': rapidapi_host
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            # Log status and body for debugging (mask key)
            masked_key = rapidapi_key[:4] + '...' if rapidapi_key else 'None'
            logging.error('RapidAPI returned status %s. Key=%s. Body=%s', resp.status_code, masked_key, resp.text)
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.exception('RapidAPI fetch failed: %s', e)
        return []

    # The RapidAPI response shape may vary. Try to discover courses in common keys.
    courses = []
    if isinstance(data, dict):
        # Check for common wrappers
        if 'courses' in data and isinstance(data['courses'], list):
            courses = data['courses']
        elif 'data' in data and isinstance(data['data'], list):
            courses = data['data']
        else:
            # Try to interpret top-level list-like fields
            for v in data.values():
                if isinstance(v, list):
                    courses = v
                    break
    elif isinstance(data, list):
        courses = data

    paths = []
    for c in courses[:max_playlists]:
        try:
            # Many RapidAPI wrappers return a flat course dict with name/title and description
            title = c.get('course_title') or c.get('title') or c.get('name') or c.get('course_name') or ''
            desc = c.get('description') or c.get('course_description') or ''
            thumb = c.get('image') or c.get('thumbnail') or ''
            course_id = str(c.get('id') or c.get('course_id') or title)[:64]

            # Represent each course as a small "path" with one video item linking to the course page
            video_obj = {
                'videoId': c.get('course_url') or c.get('url') or c.get('link') or '',
                'title': title,
                'description': desc,
                'thumbnail': thumb,
                'publishedAt': c.get('publishedAt') or c.get('created') or ''
            }

            paths.append({
                'id': course_id,
                'title': title,
                'description': desc,
                'thumbnail': thumb,
                'count': 1,
                'videos': [video_obj]
            })
        except Exception:
            logging.exception('Error normalizing RapidAPI course entry')
            continue

    return paths


def fetch_freecodecamp_learning_paths(category: Optional[str] = None, max_playlists: int = 4, items_per_playlist: int = 12, rapidapi_key: Optional[str] = None, rapidapi_host: Optional[str] = None, yt_api_key: Optional[str] = None):
    """
    Returns a list of learning paths. If RapidAPI credentials are provided, try the RapidAPI Coursera endpoint
    and normalize its results. Otherwise fall back to deriving learning paths from freeCodeCamp YouTube playlists.
    """
    # If RapidAPI info is present, use it first but only when a category (course_institution)
    # is provided. Calling the RapidAPI endpoint with an empty course_institution can
    # return a 500 from the provider, so skip RapidAPI in that case and fall back to YouTube.
    if rapidapi_key and rapidapi_host:
        if not category:
            logging.info('Skipping RapidAPI call because no category (course_institution) was provided; falling back to YouTube')
        else:
            rp = _fetch_from_rapidapi(category, max_playlists, items_per_playlist, rapidapi_key, rapidapi_host)
            if rp:
                return rp

    # Fall back to YouTube playlists
    # Prefer an explicitly passed YT API key (from app config), otherwise fall back to environment
    api_key = yt_api_key or os.environ.get('YT_API_KEY')
    if not api_key:
        logging.error('YT_API_KEY environment variable is missing and RapidAPI was not used or failed.')
        return []

    # Find playlists for the category on the freeCodeCamp channel
    search_params = {
        'key': api_key,
        'channelId': FCCC_CHANNEL_ID,
        'part': 'snippet',
        'type': 'playlist',
        'maxResults': max_playlists,
        'q': category or ''  # blank => general playlists
    }
    try:
        sr = requests.get(YOUTUBE_SEARCH_URL, params=search_params, timeout=10)
        sr.raise_for_status()
    except Exception as e:
        logging.exception('Playlist search failed: %s', e)
        return []

    items = sr.json().get('items', [])
    paths = []

    for it in items:
        try:
            playlist_id = it['id']['playlistId']
            sn = it['snippet']
            pl_title = sn.get('title', '')
            pl_desc = sn.get('description', '')
            pl_thumb = (sn.get('thumbnails', {}) or {}).get('high', {}).get('url', '')

            # Fetch first N items from the playlist
            pr = requests.get(
                YOUTUBE_PLAYLIST_ITEMS_URL,
                params={
                    'key': api_key,
                    'playlistId': playlist_id,
                    'part': 'snippet,contentDetails',
                    'maxResults': items_per_playlist
                },
                timeout=10
            )
            pr.raise_for_status()

            vids = []
            for vi in pr.json().get('items', []):
                vsn = vi.get('snippet', {}) or {}
                vids.append({
                    'videoId': (vsn.get('resourceId', {}) or {}).get('videoId', ''),
                    'title': vsn.get('title', ''),
                    'description': vsn.get('description', ''),
                    'thumbnail': (vsn.get('thumbnails', {}) or {}).get('high', {}).get('url', ''),
                    'publishedAt': vsn.get('publishedAt', '')
                })

            paths.append({
                'id': playlist_id,
                'title': pl_title,
                'description': pl_desc,
                'thumbnail': pl_thumb,
                'count': len(vids),
                'videos': vids
            })
        except Exception as e:
            logging.exception('Error building playlist path: %s', e)
            continue

    return paths