To start containers (use `--build` flag to rebuild):

```console
docker-compose up
```

To prepare tokens from `workspace/original/`
```console
docker-compose exec backend python -m CorrectOCR prepare --all --step server --loglevel DEBUG
```

To open shell on db (run in another terminal):

```console
docker exec -it $(docker ps -q --filter name=db) bash

```

To open shell on backend:

```console
docker exec -it $(docker ps -q --filter name=backend) bash

```
