import socket
import socketserver
import threading

import paramiko


def _pipe(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass


def start_ssh_docker_tunnel(host, port, username, password):
    """SSH 비밀번호 인증으로 접속한 뒤, 원격 `docker system dial-stdio`를
    로컬 TCP 포트로 이어 붙인다 (direct-streamlocal이 막혀있는 서버 대응)."""
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(hostname=host, port=port, username=username, password=password)
    transport = ssh_client.get_transport()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                channel = transport.open_session()
                channel.exec_command("docker system dial-stdio")
            except Exception:
                self.request.close()
                return
            try:
                t1 = threading.Thread(target=_pipe, args=(self.request, channel), daemon=True)
                t2 = threading.Thread(target=_pipe, args=(channel, self.request), daemon=True)
                t1.start()
                t2.start()
                t1.join()
                t2.join()
            finally:
                channel.close()

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = True

    server = Server(("127.0.0.1", 0), Handler)
    bound_port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    return server, bound_port, ssh_client
