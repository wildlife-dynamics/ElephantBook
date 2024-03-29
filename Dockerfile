FROM mambaorg/micromamba:1.4-focal

COPY environment.yml /tmp/environment.yml

RUN micromamba install --file /tmp/environment.yml --yes --name base --channel conda-forge && \
    micromamba clean --all --yes
