#!/usr/bin/env bash
set -e

docker run -it -d --name cov --mount type=bind,source="$(pwd)"/../kratos,target=/kratos keyiz/garnet-flow bash
docker exec -i cov bash -c "cd /kratos && KRATOS_COVERAGE=1 python3 -m pip install -e ."
docker exec -i cov bash -c "cd /kratos/build/temp.linux-x86_64-3.7 && make -j2"
docker exec -i cov bash -c "cd /kratos/build/temp.linux-x86_64-3.7 && make test"
docker exec -i cov bash -c "python3 -m pip install pytest && cd /kratos && pytest tests/"
docker exec -i cov bash -c "cd kratos && lcov --capture --directory . --output-file coverage.info"
# clean up coverage
docker exec -i cov bash -c "cd kratos && lcov --remove coverage.info '/usr/*' --output-file coverage.info"
docker exec -i cov bash -c "cd kratos && lcov --remove coverage.info '*extern*' --output-file coverage.info"
docker exec -i cov bash -c "cd kratos && lcov --list coverage.info"
docker cp cov:/kratos/coverage.info coverage.info

# upload the coverage file
bash <(curl -s https://codecov.io/bash) -f coverage.info