from runboat.k8s import DeploymentMode, _render_kubefiles, make_deployment_vars
from runboat.settings import BuildSettings, settings
from runboat.vcs_client import SourceInfo

EXPECTED = """\
resources:
  - pvc.yaml
  - deployment.yaml
  - service.yaml
  - ingress_odoo.yaml
  - ingress_mailhog.yaml

namespace: runboat-builds

namePrefix: "build-name-"

labels:
  - pairs:
      runboat/build: "build-name"
    includeSelectors: true
    includeTemplates: true

commonAnnotations:
  runboat/provider: "github"
  runboat/repository-id: "oca/mis-builder"
  runboat/repository-url: "https://github.com/oca/mis-builder"
  runboat/repository-full-name: "oca/mis-builder"
  runboat/source-kind: "branch"
  runboat/source-branch: ""
  runboat/target-branch: "15.0"
  runboat/review-id: ""
  runboat/commit-sha: "abcdef123456789"
  runboat/clone-url: "https://github.com/oca/mis-builder.git"

images:
  - name: odoo
    newName: "ghcr.io/oca/oca-ci"
    newTag: "py3.8-odoo15.0"
  - name: mailhog
    newName: "mailhog/mailhog"
    newTag: "latest"

secretGenerator:
  - name: odoosecretenv
    literals:
      - PGPASSWORD=thepgpassword

configMapGenerator:
  - name: odooenv
    literals:
      - PGDATABASE=build-name
      - ADDONS_DIR=/mnt/data/odoo-addons-dir
      - RUNBOAT_GIT_REPO=oca/mis-builder
      - RUNBOAT_GIT_REF=abcdef123456789
  - name: runboat-scripts
    files:
      - runboat-clone-and-install.sh
      - runboat-initialize.sh
      - runboat-cleanup.sh
      - runboat-start.sh

generatorOptions:
  disableNameSuffixHash: true

patches:
  - target:
      kind: PersistentVolumeClaim
      name: data
    patch: |-
      - op: replace
        path: /spec/storageClassName
        value: my-storage-class
  - target:
      kind: Ingress
      name: odoo
    patch: |-
      - op: replace
        path: /spec/rules/0/host
        value: build-slug.runboat.odoo-community.org
  - target:
      kind: Ingress
      name: mailhog
    patch: |-
      - op: replace
        path: /spec/rules/0/host
        value: build-slug.mail.runboat.odoo-community.org
"""


def test_render_kubefiles() -> None:
    build_settings = BuildSettings(image="ghcr.io/oca/oca-ci:py3.8-odoo15.0")
    kubefiles_path = settings.build_default_kubefiles_path
    deployment_vars = make_deployment_vars(
        mode=DeploymentMode.deployment,
        build_name="build-name",
        slug="build-slug",
        source_info=SourceInfo(
            provider="github",
            repository_id="oca/mis-builder",
            repository_full_name="oca/mis-builder",
            repository_url="https://github.com/oca/mis-builder",
            source_kind="branch",
            source_branch=None,
            target_branch="15.0",
            commit_sha="abcdef123456789",
            clone_url="https://github.com/oca/mis-builder.git",
            review_id=None,
            review_url=None,
        ),
        build_settings=build_settings,
    )
    with _render_kubefiles(kubefiles_path, deployment_vars) as tmp_path:
        assert (tmp_path / "kustomization.yaml").is_file()
        assert (tmp_path / "deployment.yaml").is_file()
        kustomization = (tmp_path / "kustomization.yaml").read_text()
        assert kustomization.strip() == EXPECTED.strip()
