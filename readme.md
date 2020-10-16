# About
CorrectOCR is a tool used to improve text from OCR processes on printed text in PDF documents.

# Documentation
Is available at [readthedocs](https://correctocr.readthedocs.io) ![Build Status](https://readthedocs.org/projects/correctocr/badge/?version=latest)

# Development
Local development is done using docker-compose: ``docker-compose up``

This command mounts code, workspace and tests directories.
It is based on the 'Dockerfile-dev' build, which doesn't include the beforementioned directories, but which is otherwise based on the production build file (Dockerfile).

Note that settings such as workspace location and database credentials can be set using CorrectOCR.INI and/or with environmental variables. 

If none of these variables are set the code has default values set.

# Important Docker commands
To start containers (use `--build` flag to rebuild):

```console
docker-compose up
```

To prepare tokens from `/app/workspace/original/`
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

# Deployment
Deployment is done using Travis-CI.
When pushing new commits, Travis-CI starts a new build, which builds a Docker image and pushes it to AWS ECR.

The deployment is then done by starting a deployment process at AWS Elastic Beanstalk, which pulls the newly build image.

# Infrastructure
The code runs as a Docker container on AWS Elastic Beanstalk.

The workspace directory is mounted on the EC2 host from EFS. This ensures, that changes in the workspace are kept if the EC2 instance is changed or the environment is rebuild.

CorrectOCR depends on a database. In production it connects to a RDS database.

Al settings concerning mounting and database connections are set using environmental variables in Elastic Beanstalk.

# History

CorrectOCR is based on code created by:

-  Caitlin Richter <ricca@seas.upenn.edu>
-  Matthew Wickes <wickesm@seas.upenn.edu>
-  Deniz Beser <dbeser@seas.upenn.edu>
-  Mitchell Marcus <mitch@cis.upenn.edu>

See their article *“Low-resource Post Processing of Noisy OCR Output for
Historical Corpus Digitisation”* (LREC-2018) for further details, it is
available online:
http://www.lrec-conf.org/proceedings/lrec2018/pdf/971.pdf

The original python 2.7 code (see `original`-tag in the repository)
has been licensed under Creative Commons Attribution 4.0
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/), see also
`license.txt` in the repository).

The code has subsequently been updated to Python 3 and further expanded
by Mikkel Eide Eriksen (mikkel.eriksen@gmail.com) for the [Copenhagen
City Archives](https://www.kbharkiv.dk/) (mainly structural changes,
the algorithms are generally preserved as-is). Pull requests welcome!
