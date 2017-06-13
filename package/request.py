# -*- coding: utf-8 -*-

# Copyright 2017 Paul Koppen
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A requests based API Client.

"""

from os.path import join as urljoin
from typing import Any, Callable, Dict, Tuple, TypeVar

from requests import Response, Session

from .client import Client

T = TypeVar('T')


class RequestClient(Session, Client):
    """A client to a HTTP requests based API.

    This class only adds the request method that will fetch from the
    server base URL configured in the child class.

    Although various implementations are possible, the design subclass
    RequestClient, adding methods that reflect API endpoints. These
    methods are easily constructed with the endpoint decorator.

    THe RequestClient inherits both from Session and from Client. The
    Session provides an easy interface to things like cookies, headers
    and authentication. The Client class serves mainly as an overarching
    construct for all possible API variations.
    """
    def request(self,
                method: str,
                path: str,
                *args: Any,
                **kwargs: Any
                ) -> Response:
        """Requests the given path, relative to the configured server.

        Args:
            method: The request method (e.g. 'GET' or 'POST').
            path: The part of the URL relative to `self.server`.
            *args: Extra arguments passed to the Session request method.
            **kwargs: Extra keyword arguments passed to the Session
                request method.

        Returns:
            The response from the server as returned by Session.request.
        """
        url = urljoin(self.server, path)
        kwargs.update(timeout=kwargs.get('timeout', 30))
        response = super().request(method, url, *args, **kwargs)
        response.raise_for_status()
        return response


class endpoint:
    """Decorator for RestClient end points.

    This really is quite a tricky class, but should be easy in its use.
    The constructor sets the parameters, which are functions that will
    parse input arguments to strings (to be put into the request). The
    __call__ method, then provides a wrapper around a given class
    method. It returns the wrapper function which takes arguments of any
    (but fixed) type that will be converted using the parameters passed
    to the constructor.

    As you can see in the example code below, the endpoint class deals
    with all aspects of the request, and the client method only needs to
    worry about the server response.

    Example:
        class MyClient(RequestClient):
            server = 'https://api.server/base/'

            @endpoint('GET', 'relative/path?q={:s}', query2str)
            def search(self, response: Response) -> MyAnswer:
                # deal with the server response here.
                # return whatever is appropriate.
                return MyAnswer(42)

        cli = MyClient()
        q = MyQuery('fin de ciecle')
        a = cli.search(q)

    In the above example, the request sent to the server is
        GET https://api.server/base/relative/path?q=fin%20de%20ciecle
    (given that a function query2str converts the query into the same
    string).

    The class also provides some class methods for convenience, allowing
    for example the above endpoint decorator to be written as:
        @endpoint.get('relative/path?q={:s}', query2str)

    Attrs:
        method: The request method.
        path_template: The path relative to the API server, possibly
            with format entities to be substituted by map args..
        map_args: A list of positional argument parsers. The endpoint
            instance will serve as a decorator on an API method. The
            decorator will receive input values which it will parse to
            strings and then substitute into the path_template. The
            functions to parse positional arguments to strings are
            provided here in *args.
        map_kwargs: A dict of keyword argument parsers. Any keyword
            arguments to the wrapper function will be parsed to string
            and sent as request parameters.
        func: The wrapped API method.
    """
    def __init__(self,
                 method: str,
                 path_template: str,
                 *args: Callable[...,str],
                 **kwargs: Callable[...,str]
                 ) -> None:
        """Creates a decorator for querying a URL end point.
        """
        self.method = method
        self.path_template = path_template
        self.map_args = args
        self.map_kwargs = kwargs
        self.func = None

    def __call__(self, func: Callable[[Response],T]) -> Callable[...,T]:
        """Wraps the endpoint decorator around a Client method.

        Args:
            func: Client method to be wrapped.

        Returns:
            The wrapper function that will invoke func.
        """
        self.func = func

        # Must return a "function", not a "method".
        return lambda *args, **kwargs: self.execute(*args, **kwargs)

    def execute(self, client: RequestClient, *args: Any, **kwargs: Any) -> T:
        """Calls func (wrapped) with the server response.

        Args:
            client: The Client instance. This is the 'self' argument of
                the method func.
            *args: Positional arguments, which will be substituted into
                path_template.
            **kwargs: Keyword arguments, which will be sent as request
                parameters.

        Returns:
            First the request is made against the server. The server
            response is then passed on to the wrapped func. We return
            func's return value.
        """
        path, params, kwargs = self._parse_args(*args, **kwargs)
        response = client.request(self.method, path, params=params, **kwargs)
        return self.func(client, response)

    def _parse_args(self, *args: Any, **kwargs: Any) -> Tuple[str,Dict[str,str],Dict[str,Any]]:
        """Fills in the request template variables.

        Args:
            *args: Positional arguments, which will be substituted into
                path_template.
            **kwargs: Keyword arguments, which will be sent as request
                parameters.

        Returns:
            A tuple with the 1. path, 2. request params and 3. remaining
            kwargs not parseable by self.map_kwargs. This last point is
            useful if you want to send extra keyword arguments to the
            request function.
        """
        args = (f(v) for f, v in zip(self.map_args, args))
        path = self.path_template.format(*args)

        params = dict()
        kwargs = dict()

        for k, v in kwargs.items():
            if k in self.map_kwargs:
                params[k] = self.map_kwargs[k](v)
            else:
                kwargs[k] = v

        return (path, params, kwargs)

    @classmethod
    def delete(cls,
               path_template: str,
               *args: Callable,
               **kwargs: Callable
               ) -> Callable:
        """Returns a DELETE endpoint."""
        return cls('DELETE', path_template, *args, **kwargs)

    @classmethod
    def get(cls,
            path_template: str,
            *args: Callable,
            **kwargs: Callable
            ) -> Callable:
        """Returns a GET endpoint."""
        return cls('GET', path_template, *args, **kwargs)

    @classmethod
    def post(cls,
             path_template: str,
             *args: Callable,
             **kwargs: Callable
             ) -> Callable:
        """Returns a POST endpoint."""
        return cls('POST', path_template, *args, **kwargs)

    @classmethod
    def update(cls,
               path_template: str,
               *args: Callable,
               **kwargs: Callable
               ) -> Callable:
        """Returns an UPDATE endpoint."""
        return cls('UPDATE', path_template, *args, **kwargs)
