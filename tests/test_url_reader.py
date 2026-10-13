import importlib
import io
import json
import sys
from pathlib import Path
from urllib.error import URLError

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/skills/external-search/scripts'))
reader = importlib.import_module('url_content_reader')


def test_html_metadata_text_and_redirect_links(monkeypatch):
    page = '<html><head><title>A &amp; B</title><meta name="description" content="A report"></head><body><p>Visible text</p><script>secret_script()</script><style>hidden_style</style><a href="../source">Source</a></body></html>'
    monkeypatch.setattr(reader, 'fetch_url', lambda *a: (page, 'text/html', 'https://example.com/reports/article'))
    result = reader.extract_url('https://example.com/start', 1, 1000)
    assert result['title'] == 'A & B'
    assert result['description'] == 'A report'
    assert 'Visible text' in result['text']
    assert 'secret_script' not in result['text']
    assert 'hidden_style' not in result['text']
    assert result['links'] == [{'text': 'Source', 'url': 'https://example.com/source'}]
    assert result['finalUrl'] == 'https://example.com/reports/article'


def test_plain_text_truncation(monkeypatch):
    monkeypatch.setattr(reader, 'fetch_url', lambda *a: ('abcdefghijklmnop', 'text/plain', 'https://example.com/file'))
    result = reader.extract_url('https://example.com/file', 1, 8)
    assert result['text'] == 'abcdefgh'
    assert result['truncated'] and result['links'] == []


def test_unknown_charset_falls_back_without_credentials(monkeypatch):
    class Response(io.BytesIO):
        headers = {'content-type': 'text/plain; charset=unknown-charset'}
        def geturl(self): return 'https://example.com/final'
    def request(req, timeout):
        assert req.get_header('Authorization') is None
        assert req.get_header('Cookie') is None
        return Response('中文内容'.encode())
    monkeypatch.setattr(reader.urllib.request, 'urlopen', request)
    text, _, final = reader.fetch_url('https://example.com/start', 1)
    assert text == '中文内容' and final == 'https://example.com/final'


def test_cli_keeps_partial_failure_and_output_contract(monkeypatch, tmp_path):
    def fetch(url, timeout):
        if url.endswith('/fail'): raise URLError('fixture unavailable')
        return ('safe content', 'text/plain', url)
    monkeypatch.setattr(reader, 'fetch_url', fetch)
    output, payload = tmp_path / 'result.html', tmp_path / 'result.json'
    monkeypatch.setattr(sys, 'argv', ['url_content_reader.py', '--data',
        json.dumps(['https://example.com/ok', 'https://example.com/fail', 'file:///local']),
        '--question', 'Read these pages', '--output', str(output), '--payload-output', str(payload)])
    assert reader.main() == 0
    data = json.loads(payload.read_text())
    assert data['type'] == 'url-content-reader'
    assert data['query'] == 'Read these pages'
    assert data['article_count'] == 1 and len(data['errors']) == 1
    assert data['urls'] == ['https://example.com/ok', 'https://example.com/fail']
    assert 'safe content' in output.read_text()


def test_batch_limit_and_missing_url(monkeypatch, tmp_path):
    requests = []
    def fetch(url, timeout):
        requests.append(url)
        return ('text', 'text/plain', url)
    monkeypatch.setattr(reader, 'fetch_url', fetch)
    monkeypatch.setattr(sys, 'argv', ['url_content_reader.py', '--data',
        json.dumps([f'https://example.com/{i}' for i in range(10)]), '--output', str(tmp_path / 'result.html')])
    assert reader.main() == 0
    assert len(requests) == 8
    monkeypatch.setattr(sys, 'argv', ['url_content_reader.py', '--url', 'file:///local', '--output', str(tmp_path / 'result.html')])
    with pytest.raises(SystemExit, match='requires at least one'):
        reader.main()


def test_html_output_escapes_extracted_content():
    document = reader.render_html({'results': [{'title': '<b>Title</b>', 'text': '<script>injected()</script>', 'url': 'https://example.com/'}]})
    assert '<script>injected()' not in document
    assert '&lt;script&gt;injected()&lt;/script&gt;' in document
    assert '&lt;b&gt;Title&lt;/b&gt;' in document
