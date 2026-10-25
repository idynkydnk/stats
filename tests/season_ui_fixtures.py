"""Render production season templates with isolated synthetic accounts for DOM checks."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_seasons import SeasonTests


def render(destination):
    case = SeasonTests()
    case.setUp()
    try:
        for i in range(60):
            case.game(i + 1, winner='Player ' + str(i),
                      day='2026-01-01' if i < 30 else '2026-01-02')
        case.game(100, division='women', winner='Women’s player')
        season = case.create()['season']
        sid = season['id']
        case.a.post('/api/seasons/' + sid + '/share', headers=case.headers)
        pages = {'form': '/seasons/new/', 'detail': '/seasons/' + sid + '/?group=doubles%3Awomen',
                 'player': '/seasons/' + sid + '/?group=doubles%3Aopen&player=B'}
        destination.mkdir(parents=True, exist_ok=True)
        for name, path in pages.items():
            response = case.a.get(path, headers=case.headers)
            assert response.status_code == 200
            (destination / (name + '.html')).write_bytes(response.data)
    finally:
        case.doCleanups()


if __name__ == '__main__':
    render(Path(sys.argv[1]))
