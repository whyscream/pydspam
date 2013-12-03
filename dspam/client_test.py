import os.path

import pytest
from flexmock import flexmock

from client import *

# Access details for an actual DSPAM instance, used in some tests
DSPAM_SOCK = 'inet:2424@localhost'
DSPAM_IDENT = 'pytest'
DSPAM_PASS = 'oka0ueVi'
DSPAM_USER = 'test'

def test_init():
    c = DspamClient()
    assert(c.socket == 'inet:24@localhost')
    assert(c.dlmtp_ident == None)
    assert(c.dlmtp_pass == None)

def test_init_with_args(tmpdir):
    sock = 'unix:' + os.path.join(str(tmpdir), 'dspam.sock')
    dlmtp_ident = 'bar'
    dlmtp_pass = 'baz'
    c = DspamClient(sock, dlmtp_ident, dlmtp_pass)
    assert c.socket == sock
    assert c.dlmtp_ident == dlmtp_ident
    assert c.dlmtp_pass == dlmtp_pass

@pytest.mark.parametrize('input,expected', [
    ('foo\r\n', 'foo\r\n'),
    ('foo\n', 'foo\r\n'),
    ('foo', 'foo\r\n'),
    ('foo\r', 'foo\r\r\n'),
])
def test_send(input, expected):
    sock = flexmock()
    sock.should_receive('send').once().with_args(expected)
    c = DspamClient()
    c._socket = sock
    c._send(input)

def test_read():
    sock = flexmock()
    sock.should_receive('recv').and_return('', 'f', 'o', 'o', '\r', '\n', 'b', 'a', 'r', '\n', 'qux').one_by_one()
    c = DspamClient()
    c._socket = sock
    assert c._read() == ''
    assert c._read() == 'foo'
    assert c._read() == 'bar'
    assert c._peek() == 'qux'

@pytest.mark.xfail(reason="Dspam is not running")
def test_connect():
    c = DspamClient(DSPAM_SOCK)
    c.connect()
    assert isinstance(c._socket, socket.socket)

def test_connect_unix_failed(tmpdir):
    sock = 'unix:' + os.path.join(str(tmpdir), 'dspam.sock')
    c = DspamClient(sock)
    with pytest.raises(DspamClientError):
        c.connect()

def test_connect_invalid_socketspec():
    sock = 'foo'
    c = DspamClient(sock)
    with pytest.raises(DspamClientError):
        c.connect()

    sock = 'foo:bar'
    c = DspamClient(sock)
    with pytest.raises(DspamClientError):
        c.connect()

def test_lhlo():
    c = DspamClient(dlmtp_ident='foo')
    flexmock(c).should_receive('_send').once().with_args('LHLO foo\r\n')
    (flexmock(c)
        .should_receive('_read')
        .times(6)
        .and_return('250-localhost.localdomain')
        .and_return('250-PIPELINING')
        .and_return('250-ENHANCEDSTATUSCODES')
        .and_return('250-DSPAMPROCESSMODE')
        .and_return('250-8BITMIME')
        .and_return('250 SIZE')
    )
    c.lhlo()
    assert c.dlmtp == True

def test_lhlo_no_dlmtp():
    c = DspamClient()
    flexmock(c).should_receive('_send').once().with_args(re.compile('^LHLO '))
    (flexmock(c)
        .should_receive('_read')
        .times(5)
        .and_return('250-localhost.localdomain')
        .and_return('250-PIPELINING')
        .and_return('250-ENHANCEDSTATUSCODES')
        .and_return('250-8BITMIME')
        .and_return('250 SIZE')
    )
    c.lhlo()
    assert c.dlmtp == False

def test_lhlo_unexpected_response():
    c = DspamClient()
    flexmock(c).should_receive('_send').once().with_args(re.compile('^LHLO '))
    flexmock(c).should_receive('_read').once().and_return('foo')
    with pytest.raises(DspamClientError):
        c.lhlo()


def test_mailfrom_invalid_args():
    c = DspamClient()
    with pytest.raises(DspamClientError):
        c.mailfrom(sender='foo', client_args='bar')

    c = DspamClient()
    c.dlmtp = False
    with pytest.raises(DspamClientError):
        c.mailfrom(client_args='foo')


@pytest.mark.parametrize('sender,dlmtp_ident,dlmtp_pass,expected', [
    (None, None, None, 'MAIL FROM:<>\r\n'),
    ('qux', None, None, 'MAIL FROM:<qux>\r\n'),
    ('qux', 'foo', None, 'MAIL FROM:<qux>\r\n'),
    # sender overrules dlmtp args
    ('qux', 'foo', 'bar', 'MAIL FROM:<qux>\r\n'),
    (None, 'foo', None, 'MAIL FROM:<>\r\n'),
    # no sender, dlmtp args are ok -> use them
    (None, 'foo', 'bar', 'MAIL FROM:<bar@foo>\r\n'),
    (None, None, 'bar', 'MAIL FROM:<>\r\n'),
])
def test_mailfrom_sender(sender, dlmtp_ident, dlmtp_pass, expected):
    c = DspamClient(dlmtp_ident=dlmtp_ident, dlmtp_pass=dlmtp_pass)
    flexmock(c).should_receive('_send').once().with_args(expected)
    flexmock(c).should_receive('_read').once().and_return('250 OK')
    c.mailfrom(sender)

def test_mailfrom_client_args():
    c = DspamClient()
    c.dlmtp = True
    flexmock(c).should_receive('_send').once().with_args('MAIL FROM:<> DSPAMPROCESSMODE="bar"\r\n')
    flexmock(c).should_receive('_read').once().and_return('250 OK')
    c.mailfrom(client_args='bar')

def test_mailfrom_error_response():
    c = DspamClient()
    flexmock(c).should_receive('_send').once()
    flexmock(c).should_receive('_read').once().and_return('451 Some error ocurred')
    with pytest.raises(DspamClientError):
        c.mailfrom()