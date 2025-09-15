"""HTTP client for making asynchronous HTTP requests with retries.

This module provides a flexible HTTP client for making RESTful API calls,
with support for customizable timeouts, automatic retries on failures,
and optional progress bars for large downloads.
"""

import requests
from tqdm import tqdm

from PyFetch.exceptions import HTTPClientError, HTTPConnectionError, ResponseError


class HTTPClient:
    """A versatile HTTP client for making requests to a web server.

    This client supports common HTTP methods (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
    and includes features like configurable timeouts, retries, and verbose logging.

    Attributes:
        timeout (int): The request timeout in seconds.
        retries (int): The number of times to retry a failed request.
        verbose (bool): If True, enables detailed logging of requests and responses.
        show_progress (bool): If True, displays a progress bar for large downloads.
        allowed_methods (list): A list of supported HTTP methods.
        MIN_SIZE_FOR_PROGRESS (int): The minimum file size in bytes to trigger the progress bar.
    """

    def __init__(self, timeout=30, retries=3, verbose=False, show_progress=False):
        """Initializes the HTTPClient with configuration options.

        Args:
            timeout (int, optional): The timeout for HTTP requests in seconds. Defaults to 30.
            retries (int, optional): The number of retry attempts for failed requests. Defaults to 3.
            verbose (bool, optional): Whether to enable verbose logging. Defaults to False.
            show_progress (bool, optional): Whether to show a progress bar for large downloads. Defaults to False.
        """
        self.timeout = timeout
        self.retries = retries
        self.verbose = verbose
        self.show_progress = show_progress
        self.allowed_methods = [
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "HEAD",
            "OPTIONS",
        ]
        self.MIN_SIZE_FOR_PROGRESS = 5 * 1024 * 1024  # 5MB

    def _create_progress_bar(self, total, desc):
        """Creates a `tqdm` progress bar if conditions are met.

        A progress bar is created if `show_progress` is True and the file size (`total`)
        is greater than or equal to `MIN_SIZE_FOR_PROGRESS`.

        Args:
            total (int): The total size of the file transfer in bytes.
            desc (str): A description to display with the progress bar.

        Returns:
            tqdm.tqdm or None: A `tqdm` progress bar instance or `None` if the conditions are not met.
        """
        if self.show_progress and total >= self.MIN_SIZE_FOR_PROGRESS:
            return tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                desc=desc,
                disable=not self.show_progress,
            )
        return None

    def _stream_response(self, response, progress_bar=None):
        """Streams the response content and updates the progress bar.

        This method iterates over the response content in chunks, allowing for efficient
        handling of large responses and real-time progress updates.

        Args:
            response (requests.Response): The HTTP response object.
            progress_bar (tqdm.tqdm, optional): The progress bar instance to update. Defaults to None.

        Returns:
            bytes: The full response content as a byte string.
        """
        chunk_size = 8192
        content = b""

        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                content += chunk
                if progress_bar:
                    progress_bar.update(len(chunk))

        if progress_bar:
            progress_bar.close()

        return content

    def make_request(self, method, url, **kwargs):
        """Makes an HTTP request with retry logic and error handling.

        This is the core method for all HTTP operations performed by the client. It handles
        request creation, response validation, retries, and exception mapping.

        Args:
            method (str): The HTTP method to use (e.g., 'GET', 'POST').
            url (str): The URL to send the request to.
            **kwargs: Additional keyword arguments to pass to the `requests.request` function.

        Returns:
            requests.Response: The HTTP response object.

        Raises:
            ValueError: If the specified HTTP method is not supported.
            HTTPConnectionError: If a connection error occurs after all retries.
            ResponseError: If an HTTP error status code is received after all retries.
            HTTPClientError: For other request-related errors.
        """
        if method.upper() not in self.allowed_methods:
            raise ValueError(
                f"Unsupported HTTP method. Allowed methods: {', '.join(self.allowed_methods)}"
            )

        # Ensure stream=True for GET requests to enable progress tracking
        if method.upper() == "GET":
            kwargs["stream"] = True

        for attempt in range(self.retries):
            if self.verbose:
                print(
                    f"[VERBOSE] Attempt {attempt + 1} of {self.retries}: Sending {method} request to {url} with {kwargs}"
                )
            try:
                response = requests.request(
                    method=method, url=url, timeout=self.timeout, **kwargs
                )
                response.raise_for_status()

                if self.verbose:
                    print(
                        f"[VERBOSE] Received response with status {response.status_code} and headers {response.headers}"
                    )

                # Handle progress indication for GET requests
                if method.upper() == "GET" and self.show_progress:
                    total = int(response.headers.get("content-length", 0))
                    progress_bar = self._create_progress_bar(
                        total, f"Downloading {url}"
                    )
                    content = self._stream_response(response, progress_bar)
                    response._content = content

                return response

            except requests.exceptions.ConnectionError as e:
                if self.verbose:
                    print(f"[VERBOSE] ConnectionError on attempt {attempt + 1}: {e}")
                if attempt == self.retries - 1:
                    raise HTTPConnectionError(
                        f"Failed to connect to {url}: {str(e)}"
                    ) from e
            except requests.exceptions.HTTPError as e:
                if self.verbose:
                    print(f"[VERBOSE] HTTPError on attempt {attempt + 1}: {e}")
                if attempt == self.retries - 1:
                    raise ResponseError(f"HTTP error occurred: {str(e)}") from e
            except requests.exceptions.RequestException as e:
                if self.verbose:
                    print(f"[VERBOSE] RequestException on attempt {attempt + 1}: {e}")
                if attempt == self.retries - 1:
                    raise HTTPClientError(f"Request failed: {str(e)}") from e

    def get(self, url, **kwargs):
        """Sends a GET request to the specified URL.

        Args:
            url (str): The URL to send the GET request to.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        """Sends a POST request to the specified URL.

        Args:
            url (str): The URL to send the POST request to.
            **kwargs: Additional keyword arguments for the request, such as `json` or `data`.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        """Sends a PUT request to the specified URL.

        Args:
            url (str): The URL to send the PUT request to.
            **kwargs: Additional keyword arguments for the request, such as `json` or `data`.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("PUT", url, **kwargs)

    def patch(self, url, **kwargs):
        """Sends a PATCH request to the specified URL.

        Args:
            url (str): The URL to send the PATCH request to.
            **kwargs: Additional keyword arguments for the request, such as `json` or `data`.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("PATCH", url, **kwargs)

    def delete(self, url, **kwargs):
        """Sends a DELETE request to the specified URL.

        Args:
            url (str): The URL to send the DELETE request to.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("DELETE", url, **kwargs)

    def head(self, url, **kwargs):
        """Sends a HEAD request to the specified URL.

        Args:
            url (str): The URL to send the HEAD request to.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("HEAD", url, **kwargs)

    def options(self, url, **kwargs):
        """Sends an OPTIONS request to the specified URL.

        Args:
            url (str): The URL to send the OPTIONS request to.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("OPTIONS", url, **kwargs)
