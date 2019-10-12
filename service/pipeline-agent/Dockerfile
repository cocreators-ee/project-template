FROM ubuntu:18.04

# Setup environment
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    ACCEPT_EULA=Y \
    PYTHONUNBUFFERED=1 \
    PATH=$PATH:/root/.pyenv/bin

ARG DEBIAN_FRONTEND=noninteractive
ARG DEBCONF_NONINTERACTIVE_SEEN=true

# Install basic command-line utilities
RUN set -exu \
 && echo -e "nameserver 1.1.1.1\nnameserver 8.8.8.8" > /etc/resolv.conf \
 && echo "tzdata tzdata/Areas select Etc" > /tmp/preseed.txt \
 && echo "tzdata tzdata/Zones/Etc select UTC" >> /tmp/preseed.txt \
 && debconf-set-selections /tmp/preseed.txt \
 && rm -f /etc/timezone \
 && rm -f /etc/localtime \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    apt-transport-https \
    build-essential \
    bzip2 \
    ca-certificates \
    curl \
    dnsutils \
    file \
    git \
    gnupg \
    iproute2 \
    iputils-ping \
    libbz2-dev \
    libffi-dev \
    liblzma-dev \
    libncurses5-dev \
    libncursesw5-dev \
    libreadline-dev \
    libssl-dev \
    libsqlite3-dev \
    locales \
    lsb-core \
    lsb-release \
    mercurial \
    openssh-client \
    openssl \
    python-openssl \
    shellcheck \
    software-properties-common \
    sudo \
    time \
    tzdata \
    unattended-upgrades \
    unzip \
    wget \
    zip \
    zlib1g \
    zlib1g-dev \
 && update-ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN set -exu \
 && locale-gen $LANG \
 && update-locale

# Install Docker
RUN set -exu \
 && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add - \
 && add-apt-repository -y "deb [arch=amd64] https://download.docker.com/linux/ubuntu bionic stable" \
 && apt-get update \
 && apt-cache policy docker-ce-cli \
 && apt-get install -y --no-install-recommends \
    docker-ce-cli \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Install Azure CLI (instructions taken from https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
RUN set -exu \
 && echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $(lsb_release -cs) main" \
  | tee /etc/apt/sources.list.d/azure-cli.list \
 && curl -L https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
 && curl -L https://packages.microsoft.com/keys/msopentech.asc | apt-key add - \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    azure-cli \
 && az --version \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN set -exu \
 && curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl \
 && chmod +x ./kubectl \
 && mv ./kubectl /usr/local/bin/kubectl

# Install Python
RUN set -exu \
 && curl https://pyenv.run | bash \
 && eval "$(pyenv init -)" \
 && eval "$(pyenv virtualenv-init -)" \
 && pyenv install -l \
 && pyenv install 3.6.9 \
 && pyenv global 3.6.9 \
 && pyenv rehash \
 && bash -r \
 && curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py \
 && python get-pip.py \
 && rm get-pip.py \
 && pyenv rehash \
 && bash -r \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN set -exu \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        software-properties-common \
 && apt-add-repository ppa:git-core/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        apt-utils \
        curl \
        git \
        jq \
        libcurl4 \
        libicu60 \
        libunwind8 \
        netcat \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && rm -rf /etc/apt/sources.list.d/*

# Accept the TEE EULA
RUN mkdir -p "/root/.microsoft/Team Foundation/4.0/Configuration/TEE-Mementos" \
 && cd "/root/.microsoft/Team Foundation/4.0/Configuration/TEE-Mementos" \
 && echo '<ProductIdData><eula-14.0 value="true"/></ProductIdData>' > "com.microsoft.tfs.client.productid.xml"

# Install build environment dependencies
RUN set -exu \
 && curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python \
 && wget "https://github.com/instrumenta/kubeval/releases/download/0.13.0/kubeval-linux-amd64.tar.gz" \
 && tar -xf "kubeval-linux-amd64.tar.gz" \
 && chmod +x kubeval \
 && mv kubeval /usr/local/bin \
 && wget "https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.9.1/kubeseal-linux-amd64" -O kubeseal \
 && chmod +x kubeseal \
 && mv kubeseal /usr/local/bin

# Clean system
RUN set -exu \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /root/.cache

WORKDIR /vsts

COPY ./start.sh .
RUN chmod +x start.sh

CMD ["bash", "start.sh"]
