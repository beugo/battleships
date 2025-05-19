# Battleships

The following third-party packages are required:

* `rich`
* `pycryptodome`
* `prompt_toolkit`

To install these requirements, run the following command:

```
pip install -r requirements.txt
```

To start up the server, simply run:

```
python3 server.py
```

In the project directory. The server will start listening for clients.
In a separate terminal, run:

```
python3 client.py
```

The client will automatically connect to the running server. To run multiple clients, simply run the same command in new terminals.