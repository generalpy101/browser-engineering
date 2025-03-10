import socket
import ssl
from typing import DefaultDict, Tuple

ALLOWED_PROTOCOLS = ("http", "https")


class Url:
    HTTP_GET_STRING = """GET {path} HTTP/1.1
Host: {hostname}
Connection: close
User-Agent: Pybrowser
    """

    def __init__(self, url) -> None:
        self.url = url
        self.protocol, self.hostname, self.path, self.port = self.parse_url()

    def request(self, **headers) -> Tuple[int, DefaultDict[str, str], str]:
        """
        Send a request to the server and return the status code, headers and body
        Only support GET method for now
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if self.protocol == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=self.hostname)

        sock.connect((self.hostname, self.port))
        request_string = self._create_request_string(headers)
        sock.send(request_string.encode())

        response_obj = sock.makefile("r", encoding="utf8", newline="\r\n")
        response = response_obj.read()
        sock.close()

        return self.parse_http_response(response)
    
    def _create_request_string(self, headers) -> str:
        """
        Create the request string with headers
        """
        request_string = f"GET {self.path} HTTP/1.0\r\n"
        request_string += f"Host: {self.hostname}\r\n"
        # Add default headers
        request_string += "Connection: close\r\n"
        request_string += "User-Agent: Pybrowser\r\n"
        # Add user supplied headers
        for key, value in headers.items():
            request_string += "{}: {}\r\n".format(key, value)
        request_string += "\r\n"
        print(request_string)
        return request_string

    def parse_http_response(self, response: str) -> Tuple[int, DefaultDict[str, str], str]:
        """
        Parse the http response and return status code, headers and body
        """
        headers, body = response.split("\r\n\r\n", 1)
        headers = headers.split("\n")
        status_code = int(headers[0].split(" ")[1])
        headers = dict([h.split(": ") for h in headers[1:]])
        return status_code, headers, body

    def parse_url(self) -> Tuple[str, str, int]:
        """
        Parse the url into protocol, hostname, path and port
        """
        protcol, link = self.url.split("://")
        assert protcol in ALLOWED_PROTOCOLS
        if "/" in link:
            hostname, path = link.split("/", 1)
        else:
            hostname, path = link, "/"

        if ":" in hostname:
            port = int(hostname.split(":")[1])
            hostname = hostname.split(":")[0]
        else:
            port = 80 if protcol == "http" else 443

        if path == "":
            path = "/"

        return protcol, hostname, path, port
    
def show_html(content):
    '''
    Display the content of the html page
    '''
    in_tag = False
    for char in content:
        if char == "<":
            in_tag = True
        elif char == ">":
            in_tag = False
        elif not in_tag:
            print(char, end="")

def main():
    url = Url("http://www.example.com/")
    status_code, headers, body = url.request()
    assert status_code == 200
    show_html(body)

if __name__ == "__main__":
    main()