[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![SonarCloud analysis](https://sonarcloud.io/api/project_badges/measure?project=Lieturd_project-template&metric=alert_status)](https://sonarcloud.io/dashboard?id=Lieturd_project-template)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Travis-CI build status](https://travis-ci.org/Lieturd/project-template.svg?branch=master)](https://travis-ci.org/Lieturd/project-template)

# Lieturd project template

This project template is meant for use by anyone and everyone, it's aim
is to promote good practices and make it easy to kick-start a project.

It does some assumptions however:

 - You want to use [Azure DevOps](https://dev.azure.com/) with it (if
   you haven't tried it before, you should check it out).
 - You mostly deploy Docker images to Kubernetes
 - You use Yaml for your Kubernetes configuration
 - You are comfortable with using Python >=3.6 at least for your tooling
 - You use Git (though usage with e.g. Mercurial is reasonably easy)
 - You like using [pre-commit](https://pre-commit.com) for your hooks
 - You use [minikube](https://github.com/kubernetes/minikube) (but any
   other local Kubernetes should work fine with minimal changes)
 - You would like [kured](https://github.com/weaveworks/kured) to manage
   the restarting of your Kubernetes nodes automatically
 - You want to store secrets in encrypted form in your repository using
   [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)

It works especially well for projects where you build Python APIs as the
tooling already uses Python. However, you can really build anything else
with it as well and this template aims to prove that.


## Pre-requisites

Every machine where you run projects based on this, perform builds,
releases or similar should likely have the following installed:

 - [Python >=3.6](https://www.python.org/downloads/)
 - [Poetry](https://poetry.eustace.io)
 - [Kubeval](https://kubeval.instrumenta.dev/installation/)
 - [Kubeseal](https://github.com/bitnami-labs/sealed-secrets/releases)
 - [Git](https://git-scm.com/downloads)
 - [Minikube](https://github.com/kubernetes/minikube) for local env

To save some effort, you can use the Azure DevOps pipeline agent in
this repository's `service/pipeline-agent`. You'll need to buy the
dedicated agent slots on Azure DevOps for it though, so you might want
to start with the hosted agents.

If you do use it, configure `service/pipeline-agent/kube/01-config.yaml`
and create the related sealed secrets for it. `VSTS_TOKEN` needs to be
created from Azure DevOps. More information at [https://hub.docker.com/_/microsoft-azure-pipelines-vsts-agent](https://hub.docker.com/_/microsoft-azure-pipelines-vsts-agent)


## Directory structure, components, and naming

The directory structure should be fairly self-explanatory.

 - `tasks.py` - Contains [Invoke](http://docs.pyinvoke.org/) tasks run
   via `poetry run invoke ...`
 - `azure-devops` - Contains the Azure DevOps pipeline configurations
 - `devops` - Contains the bulk of the DevOps -tooling code
 - `envs` - Contains configuration for environments
 - `kube` - Basic configuration for all Kubernetes clusters

You will find many commands and configs refer to "components". It is
used simply to refer to the *path* with a `Dockerfile` and `kube/*.yaml`
that can be used to build and deploy your things to Kubernetes.

The repository contains the example component `service/pipeline-agent`
and the build and release configurations for it.

Naming works as follows:

 - Components: `path/to/component` -> `{IMAGE_PREFIX}-path-to-component`
   in e.g. Docker repository names. This means that if you configure
   `devops/settings.py` with `IMAGE_PREFIX = "myproj"`, then
   `service/pipeline-agent` will be built as
   `myproj-service-pipeline-agent` and you need to use that name for it
   in Kubernetes configs and in some pipeline variables.
 - Kubernetes Deployments etc.: Typically use the last component or last
   components of the path that are unique, e.g. `service/pipeline-agent`
   -> `pipeline-agent`, or `api/user/v1` -> `user-v1`. Use the same name
   for Deployment and Service for simplicity.
 - Pipelines: `Build|Release <component name>` - unfortunately it seems
   Azure DevOps does not respect the `name` property and you have to
   rename them manually after creation.
 - Pipeline configs: `(build|release)-<component name>.yml`

For deleting old Kubernetes resources, you can move your `.yaml` file under `kube/obsolete/` and it will be picked up AFTER the release of the `kube/*.yaml` files have been applied and the resources will be deleted.

The `envs` have a few things to keep in mind.

Firstly, every `envs/*` is expected to be run on one Kubernetes cluster
(except `minikube`), though mostly because of Sealed Secrets keys (in
`envs/<env>/secrets.pem`) and such things not being considered for
distribution.

Secondly, you should store the sealed secrets generated with `kubeseal`
to `envs/<env>/secrets/<num>-<name>.yaml`, e.g. `01-pipeline-agent.yaml`
and they will be applied during release. Similarly the files in
`envs/<env>/secrets/obsolete/` will have their resources deleted.

Thirdly, if you need to override any component's `kube/` configs, you
can store an override to `envs/<env>/component/path/kube/<file>.yaml`,
e.g. `api/test/v1/kube/01-config.yaml` could be overridden for `staging`
env by creating `envs/staging/api/test/v1/kube/01-config.yaml` with the
full replacement contents.

If you want to do purely local settings for `devops` scripts, e.g. to
change the `LOG_LEVEL`, you can create `devops/settings_local.py` with
your overrides.

### Yaml merges

In the `envs/<env>/merges/` folder you can put files to merge with your
existing configs.

E.g. if you want to just override one field, add one setting, or remove
some specific thing, you don't need to replace the whole file. This will
help with reducing duplication and thus risking your settings getting
out of sync.

To remove previously defined properties, set the value as `~`.

To skip items in lists (leave them untouched), just use an empty value as in:

```
list:
 - # Skipped
 - override
```

If you need to skip a full YAML document on a multi-document file, make
sure the YAML parser understands that. E.g. to skip the first document
you will need to do something like:

```yaml
---
---
# Document 2
spec:
  value: override
```

Otherwise it should work pretty much as expected. Any items in original
file that do not exist in overrides, stay untouched. Any new items are
added. Any string/number/similar values on both get replaced.

As a specific example, if you have `component/kube/01-example.yaml` and
`envs/test/merges/component/kube/01-example.yaml` with the contents:

```yaml
# component/kube/01-example.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: myproj-settings
data:
  MY_SETTING: "foo"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
spec:
  selector:
    matchLabels:
      app: my-deployment
  template:
    metadata:
      labels:
        app: my-deployment
    spec:
      containers:
        - name: my-container
          imagePullPolicy: IfNotPresent
          image: my-container:latest
          env:
            - name: ANOTHER_SETTING
              value: some-value
          volumeMounts:
            - mountPath: /var/run/docker.sock
              name: docker-volume
```

and

```yaml
# envs/test/merges/component/kube/01-example.yaml
data:
  MY_SETTING: "bar"
---
spec:
  template:
    spec:
      containers:
        - env:
            - name: ANOTHER_SETTING # this prop is here just for clarity
              value: another-value
          volumeMounts: ~
          livenessProbe:
            exec:
              command:
               - cat
               - /tmp/healthy
            initialDelaySeconds: 5
            periodSeconds: 5
```

You will end up afterwards with a processed combination of:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: myproj-settings
data:
  MY_SETTING: "bar"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
spec:
  selector:
    matchLabels:
      app: my-deployment
  template:
    metadata:
      labels:
        app: my-deployment
    spec:
      containers:
        - name: my-container
          imagePullPolicy: IfNotPresent
          image: my-container:latest
          env:
            - name: ANOTHER_SETTING
              value: another-value
          livenessProbe:
            exec:
              command:
               - cat
               - /tmp/healthy
            initialDelaySeconds: 5
            periodSeconds: 5
```


## Post-release actions

When you need to e.g. perform database migrations after release, the
tooling can help out. In any component directory you can create a file
`post-release.sh`, which will be automatically executed on a random pod
after the resources have been restarted.

In practice when e.g. writing database migrations for your Python API
you might want that script to run something like:

 - [migrate-anything](https://github.com/Lieturd/migrate-anything)
 - [yoyo-migrate](https://ollycope.com/software/yoyo/latest/)
 - [flyway](https://flywaydb.org)
 - [pymongo-migrate](https://github.com/stxnext/pymongo-migrate)


## Taking the template into use

1. Download the latest release of this repository
1. Create an Azure DevOps project if you don't have one yet
1. Maybe remove `.travis.yml` if you don't want Travis-CI integration to
   [SonarCloud](https://sonarcloud.io/)
1. Update or remove `LICENSE.md`
1. Update this file for your needs
1. Configure [devops/settings.py](devops/settings.py), especially `IMAGE_PREFIX`
1. Update `kured-config` in [kube/02-kured.yaml](kube/02-kured.yaml)
1. Create `envs/*/settings.py` for the environments you wish to manage
1. Run `poetry run invoke init-kubernetes <env>` for every relevant
   Kubectl context (incl. `minikube`) - keep in mind we assume one
   cluster per env.
1. Modify `azure-devops/*.yml` `variables` to match your settings
1. Update `azureSubscription` in `azure-devops/*.yml`
1. Set up necessary Service Connections from Azure DevOps to Azure and
   configure `azure-devops/*.yml` accordingly.
1. Commit the `envs/*/secrets.pem` -files
1. Convert any existing secrets with [kubeseal](https://github.com/bitnami-labs/sealed-secrets/#usage) using
   `--cert envs/<env>/secrets.pem` -arg.
1. Commit and push all changes to your Azure DevOps project
1. Enable [Multi-stage pipelines](https://devblogs.microsoft.com/devops/whats-new-with-azure-pipelines/) from [preview features](https://docs.microsoft.com/en-us/azure/devops/project/navigation/preview-features?view=azure-devops) (possibly optional)
1. Add pipelines from the `azure-devops/*.yml` -files AND manually
   configure the automatic post-build triggers as necessary (e.g. to
   release after master build)
1. Try to run the pipelines and then "Authorize" them in Azure DevOps
   or fix missing service connections and such.


## Development usage

Every developer checking out the repository should first run

```bash
minikube start [--cpus=4] [--memory=4g] [--disk-size=50g]
minikube docker-env
# Follow instructions from output
poetry install
poetry run invoke init
```

For most projects you should set up `ksync` or similar, or to run
```bash
minikube mount .:/src --ip=$(minikube ip)
```

These will configure the hooks and minikube environment.

To restart from scratch, just run `minikube delete` and start again.


## Other common commands

```bash
# Releasing specific version for specific component
poetry run invoke release <env> \
    --component service/pipeline-agent \
    --image service/pipeline-agent=<name>.azurecr.io/project-service-pipeline-agent \
    --tag service/pipeline-agent=master-994ee2d-20191012-141539

# Build a specific component
poetry run invoke build-images --component service/pipeline-agent

# Clean up the Azure Container Registry, name is from <name>.azurecr.io
poetry run invoke cleanup-registry <name>
```


## Initializing Azure Kubernetes Service -cluster

For setting up everything to work nearly with this template on AKS, you
should run a few commands afterwards.

First, ensure your `kubectl` context is set correctly (`kubectl config get-contexts` and `kubectl config use-context <ctx>`).

1. If you didn't create the AKS cluster with `--attach-acr` then you
   should create a service principal for your AKS cluster to access ACR.

```bash
# Set up pull permissions to ACR from this cluster so we don't need
# imagePullSecrets in all kube configs.

# Get the id of the service principal configured for AKS
CLIENT_ID=$(az aks show --resource-group $AKS_RESOURCE_GROUP --name $AKS_CLUSTER_NAME --query "servicePrincipalProfile.clientId" --output tsv)

# Get the ACR registry resource id
ACR_ID=$(az acr show --name $ACR_NAME --resource-group $ACR_RESOURCE_GROUP --query "id" --output tsv)

# Create role assignment
az role assignment create --assignee $CLIENT_ID --role acrpull --scope $ACR_ID
```

2. The dashboard typically needs permissions that are not there by
   default.

```bash
# Set up permissions for dashboard
kubectl create clusterrolebinding kubernetes-dashboard -n kube-system --clusterrole=cluster-admin --serviceaccount=kube-system:kubernetes-dashboard
```


## Important information

### Security of secrets

For the `minikube` env the scripts will automatically store the master
key for Sealed Secrets in the repo, and restore it from there to all dev
environments. This is so you can also use Sealed Secrets in dev and not
run into problems in other environments.

However this also means that the secrets stored for `minikube` are *NOT
SECURE*. Do not put any real secrets in them without being fully aware
of the consequences.

For all other environments you are expected to store the `secrets.pem`
for each environment in the repository, and the sealed secrets in
encrypted form in `envs/<env>/secrets/*.yaml`.

For example:

```bash
# Create a secret, output as yaml to a file and don't run on server
kubectl create secret my-secret \
    -o yaml \
    --dry-run \
    --from-literal=foo=bar > my-secret.yaml
kubeseal --cert envs/<env>/secrets.pem < my-secret.yaml > envs/<env>/secrets/01-my-secret.yaml
```

You might also want to back-up your master key, but do NOT store it in
the repository - put it safely away in e.g. your password manager's
secure notes -section.


### License

The project template is released with the BSD 3-clause license. Some of
the tools used might use other licenses. Please see [LICENSE.md](./LICENSE.md) for more.

While this is not GPL/LGPL/similar, if you improve on the template,
especially anything on the TODO, contribution back to the source would
be appreciated.

You will likely want to update that file for your own private projects.

### Build names

If you choose to use a different build name, you should likely update
`cleanup_acr_repository` in `tasks.py` and fix `_sort_tag` for your
names.

### Questions & Answers

**Q: Why do you not use `ctx.run` for Invoke tasks?**

A:
> It has been unreliable, especially when you run a large number of
> small tasks - sometimes just raising `UnexpectedExit` with no exit
> code or output at all.

**Q: Why do you use Alpine Linux base images?**

A:
> The minimal distribution makes builds and releases faster, and
> reduces attack footprint.

**Q: Why do you use `/bin/sh` (or `#!/usb/bin/env sh`) instead of BASH?**

A:
> Compatibility with busybox etc., especially Alpine Linux.

**Q: How to optimize Dockerfile build speeds?**

A:
> First, use `verdaccio` and `devpi` and such caches hosted locally.
> Secondly, use pipeline caching. Thirdly, make sure you split your
> `Dockerfile` in steps so your commands are:
>
> 1. Set up environment, args, other things that basically never change
> 2. Install the build dependencies and other such always required pkgs
> 3. Copy the project dependency configuration for `npm`, `poetry` etc.
> 4. `RUN` the task to install dependencies based on that configuration
> 5. `COPY` the source files over
> 6. `RUN` any final configuration, incl. deletion of build deps
>
> This way Docker's cache gets invalidated less often.

### TODO

Things that could be done better still:

 - Invoke tasks: Create a `dev` task that automatically runs various
   tests, maybe uses e.g. [ksync](https://vapor-ware.github.io/ksync/)
   and such.
 - Azure DevOps: Use of [templates](https://docs.microsoft.com/en-us/azure/devops/pipelines/process/templates?view=azure-devops)
 - Azure DevOps: Examples of [pipeline caching](https://docs.microsoft.com/en-us/azure/devops/pipelines/caching/index?view=azure-devops)
 - Azure Key Vault: Examples of [Key Vault](https://azure.microsoft.com/en-us/services/key-vault/) use for secure storage of secrets
 - Kubernetes RBAC: Limiting privileges each user has for the non-local
   environments.
 - DevSecOps: E.g. automatic security scans of build containers
 - Automated tests: Good examples for how to run automated tests after
   components have been built
 - Env setup tools: Simple tools to deploy a new named environment
 - Dashboard RBAC: Does it really need that high level of permissions?
 - Backup: Automated tool to back up important configuration e.g. Sealed
   Secret master keys
 - DevOps scripts: Unit tests, probably based on `--dry-run` mode
 - Caches: Add examples of usage of [Verdaccio](https://verdaccio.org)
   and [devpi](https://devpi.net/docs/devpi/devpi/stable/%2Bd/index.html)
 - Azure DevOps: It would be nice to be able to set variables with a
   form, especially things like the tag for release
 - Releases: Examples of real functional database migrations using
   [migrate-anything](https://github.com/Lieturd/migrate-anything)
