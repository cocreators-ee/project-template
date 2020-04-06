import subprocess

import pytest
from ruamel.yaml import YAML

from devops.settings import TEMPLATE_HEADER, UNSEALED_SECRETS_EXTENSION
from devops.tasks import (
    base64_decode_secrets,
    base64_encode_secrets,
    get_master_key,
    kubeval,
    seal_secrets,
    unseal_secrets,
    update_from_templates,
)
from devops.tests.conftest import TEST_ENV, TEST_ENV_PATH
from devops.tests.test_utils import (
    TEST_COMPONENT_OVERRIDE_TEMPLATE,
    TEST_COMPONENT_OVERRIDE_TEMPLATE_PATH,
    TEST_COMPONENT_RENDERED_OVERRIDE,
    TEST_COMPONENT_RENDERED_OVERRIDE_PATH,
    TEST_ENV_SETTINGS,
    TEST_SETTINGS,
    TEST_SETTINGS_WITH_VARIABLES,
)

TEST_ENV_SECRETS_PATH = TEST_ENV_PATH / "secrets"
TEST_ENV_SEALED_SECRETS_PATH = TEST_ENV_SECRETS_PATH / "01-test-secrets.yaml"
TEST_ENV_UNSEALED_SECRETS_PATH = TEST_ENV_SECRETS_PATH / (
    "01-test-secrets" + UNSEALED_SECRETS_EXTENSION
)

BASE64_DECODED_SECRETS = """
apiVersion: v1
data:
  password: abcåäö
  private_key: |
    -----BEGIN RSA PRIVATE KEY-----
    MIICXgIBAAKBgQDGWkiZd7sILeW2NszfkTahxoYKFqj8TfPOX4rLwhCJr0OkppnZ
    oePopFzkyqXS+q1UrQ5qoxF25ks0hDoYW7bTlTxyBOiVZ9BqelJP+jMRlaDFOQV3
    SPlSip4SAbUgey69SyXik4ZxZTP8+vSy5MoqBe0ZpH7u5U3gNIYfGfJF6QIDAQAB
    AoGAMwNPPqELahwbwxQu9qSrL0oWeQvA5DrMJFxwHt1HUZHQzMzILq+zJMb42SLB
    KRStdWSYm5ZazICIAPas1kzoJOhRnZnh8iwwkoyCtjjUJ9leZAxoLZqx2cKu9O3f
    8Hlr/52erNs/qpi59NmyN5N3XqZcgmK63kTZM0NxRjf1tQECQQDvieSWKyJai+zW
    jLZ7OnmxZbR6oSlIJ08+ZuPKj19jYjocvajD3T2DoNSMqOf32JD3buk7Wwydne5S
    +Kg8CfaJAkEA0/vSiDfCspTm6LkeapkEjm2Pdp+Rzletx3FvDqB8d2cJ0Rm9gr01
    RcOdghH/LamG/I2UKg8bMfX2J4hOMFX8YQJBAOAPRehJlKrJs9HEcXS279nF3pnO
    YgUB8BfYuj5g+cLGwMDdjx0Wt1GGgQrJe6HTy1YHQtaohhZxAdpOiV8PmrECQQCY
    rmEF8buO6oaiCmto9ct9VlYlZ2saRraI1x/ZVigvzAwbCkIf/212UR2KSLIVzmvG
    Tabw4C6DPpfMA3XlhJkhAkEAoIcAcIwMxj2i46WdlSL8zt/5EAgeF0jdCLJPU6J5
    xrbc46CIEyiNKpyhIdDOcZqsUevytVTyOxSnnsOYBdW5LA==
    -----END RSA PRIVATE KEY-----
kind: Secret
metadata:
  name: test-secrets
  namespace: default
type: Opaque
"""

TEST_ENV_SECRETS_PEM = TEST_ENV_PATH / "secrets.pem"

SECRETS_PEM = """
-----BEGIN CERTIFICATE-----
MIIErjCCApagAwIBAgIRANO1s7QI5T9JyT5slOSD+gowDQYJKoZIhvcNAQELBQAw
ADAeFw0yMDAxMDkxMjIxMjVaFw0zMDAxMDYxMjIxMjVaMAAwggIiMA0GCSqGSIb3
DQEBAQUAA4ICDwAwggIKAoICAQC8eS6Gv4EEjAOtJxw859OO4fzf2w7t92+WcBUs
JnsjDo0eXZSo3uoGmZ3ROgmallAPPB3qYVXVuD5et5ZnsbOLwGLUI5n4Hd1jmtAj
M7aLhpg4YY69gc1vT/OBsDWHuGZpnftiyi6Kh+e+gA0l7vMHTxyxNQhx4/EIJwio
k0JJw5TyMQwdXCdi0fAoqPW+hQEx+KJk29IKzu4nhCAx+fLP4nKQqiYNP1wYeSel
frK5fxc702vX8Mwa2TMgL4jZyILiEFS3EF49VypXyu3Mp9voqr/zJbxWTq6cH40n
QEwxedBKOW8bo9ykoOhYG0V4AveUa+Ns9vetjhXTwhXJ+LoNX93sxuXZTUgEcImu
i/0UV4Ta/zF8jdvOi99Fdx+uzcgWI77bmRJ+Ko3Cfp0KHL3SwY1VUwoKQ+ehiYTK
8kUaSy/jna1A45nwFaMAIFDZ6lzPUx5A+Yqap/cAak/vwt2UoFrMa/NCbMvUS25z
rYa9c68FT3Abd9b7Tr8t2qSI97w45TVUYBk1c+xAGgl+Sq3zfPJIGfh1BcVmp5kf
VPFCLoOnWKcTEzAzpKhxK8+l1wrxujHibjy8YtfYTobDc6QcKZKjglKnHZu+OOLd
XxkEFowe9aalUQrg1bGe45Cr1CNNlOxWG+qO0mfXXHysFdu9FZ743qzMJLyezLb2
Y/5qgQIDAQABoyMwITAOBgNVHQ8BAf8EBAMCAAEwDwYDVR0TAQH/BAUwAwEB/zAN
BgkqhkiG9w0BAQsFAAOCAgEAnp1bQvGM6ax5AA36rvFki7SAIUj8N5VMo+uVVfDL
eJeRtab6l/ZM0vM+UybNMjp513d/RVWcPBQcoMwG6Z61raUJjabzGEXM+H9jWrxl
YNqJRBAoJEAe1kBwqJ7IYb51tzXoeSw5J1K0cEwXdNtawRSSURYScnNYA7qaHJHo
Bl6fKpK+oS7LT4NbgQAft42ednrMkXIUbh9JED9ayZUj2VZBn445xDMOgQVfFwuB
YtAblf6p96UOlO0XPM4hLQIaf/m/Yp6ye+5lAju2XMBU/jwBV/p4Gl5Xt0HZMU9a
aXI5UcT8h5Ktp2OcipJkPhI3zg6WGq/04akzd2sQR6hXOe2qyjrxXjpuBwxOa8Ud
SwZPUv4AjnTDv3jwakvmOeQVWQCTpLQBCkJ41lLNWqCvlhKr/XZzxeSJqIMAFAV0
BayKKqv0hC7XlVnpY0OORq8VranhjZRAorqYvjEnz4Ec3GTrgerLsARorxWAn0HR
UamdfqYybZ0FoLILqAdO8c9Z3nc+MCzXYM1Lo4GeBqGRfo1UyyckyG+z7pAgnaD6
RnuYQ88awKoOsOlcVkllVsiTapcLEDUBKWEDBh/5da7f2YteE8rsC4nXlWn8jrDZ
OTUFO9eaYZSp2uKmKgnYVlPazAGtNKYOOBg2j1xk00EF0KX0ANVTXdOiA+32cyeS
2/w=
-----END CERTIFICATE-----
"""

TEST_ENV_MASTER_KEY = TEST_ENV_PATH / "master.key"

MASTER_KEY = """
apiVersion: v1
items:
- apiVersion: v1
  data:
    tls.crt: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUVyakNDQXBhZ0F3SUJBZ0lSQU5PMXM3UUk1VDlKeVQ1c2xPU0QrZ293RFFZSktvWklodmNOQVFFTEJRQXcKQURBZUZ3MHlNREF4TURreE1qSXhNalZhRncwek1EQXhNRFl4TWpJeE1qVmFNQUF3Z2dJaU1BMEdDU3FHU0liMwpEUUVCQVFVQUE0SUNEd0F3Z2dJS0FvSUNBUUM4ZVM2R3Y0RUVqQU90Snh3ODU5T080ZnpmMnc3dDkyK1djQlVzCkpuc2pEbzBlWFpTbzN1b0dtWjNST2dtYWxsQVBQQjNxWVZYVnVENWV0NVpuc2JPTHdHTFVJNW40SGQxam10QWoKTTdhTGhwZzRZWTY5Z2MxdlQvT0JzRFdIdUdacG5mdGl5aTZLaCtlK2dBMGw3dk1IVHh5eE5RaHg0L0VJSndpbwprMEpKdzVUeU1Rd2RYQ2RpMGZBb3FQVytoUUV4K0tKazI5SUt6dTRuaENBeCtmTFA0bktRcWlZTlAxd1llU2VsCmZySzVmeGM3MDJ2WDhNd2EyVE1nTDRqWnlJTGlFRlMzRUY0OVZ5cFh5dTNNcDl2b3FyL3pKYnhXVHE2Y0g0MG4KUUV3eGVkQktPVzhibzl5a29PaFlHMFY0QXZlVWErTnM5dmV0amhYVHdoWEorTG9OWDkzc3h1WFpUVWdFY0ltdQppLzBVVjRUYS96RjhqZHZPaTk5RmR4K3V6Y2dXSTc3Ym1SSitLbzNDZnAwS0hMM1N3WTFWVXdvS1ErZWhpWVRLCjhrVWFTeS9qbmExQTQ1bndGYU1BSUZEWjZselBVeDVBK1lxYXAvY0Fhay92d3QyVW9Gck1hL05DYk12VVMyNXoKcllhOWM2OEZUM0FiZDliN1RyOHQycVNJOTd3NDVUVlVZQmsxYyt4QUdnbCtTcTN6ZlBKSUdmaDFCY1ZtcDVrZgpWUEZDTG9PbldLY1RFekF6cEtoeEs4K2wxd3J4dWpIaWJqeThZdGZZVG9iRGM2UWNLWktqZ2xLbkhadStPT0xkClh4a0VGb3dlOWFhbFVRcmcxYkdlNDVDcjFDTk5sT3hXRytxTzBtZlhYSHlzRmR1OUZaNzQzcXpNSkx5ZXpMYjIKWS81cWdRSURBUUFCb3lNd0lUQU9CZ05WSFE4QkFmOEVCQU1DQUFFd0R3WURWUjBUQVFIL0JBVXdBd0VCL3pBTgpCZ2txaGtpRzl3MEJBUXNGQUFPQ0FnRUFucDFiUXZHTTZheDVBQTM2cnZGa2k3U0FJVWo4TjVWTW8rdVZWZkRMCmVKZVJ0YWI2bC9aTTB2TStVeWJOTWpwNTEzZC9SVldjUEJRY29Nd0c2WjYxcmFVSmphYnpHRVhNK0g5aldyeGwKWU5xSlJCQW9KRUFlMWtCd3FKN0lZYjUxdHpYb2VTdzVKMUswY0V3WGROdGF3UlNTVVJZU2NuTllBN3FhSEpIbwpCbDZmS3BLK29TN0xUNE5iZ1FBZnQ0MmVkbnJNa1hJVWJoOUpFRDlheVpVajJWWkJuNDQ1eERNT2dRVmZGd3VCCll0QWJsZjZwOTZVT2xPMFhQTTRoTFFJYWYvbS9ZcDZ5ZSs1bEFqdTJYTUJVL2p3QlYvcDRHbDVYdDBIWk1VOWEKYVhJNVVjVDhoNUt0cDJPY2lwSmtQaEkzemc2V0dxLzA0YWt6ZDJzUVI2aFhPZTJxeWpyeFhqcHVCd3hPYThVZApTd1pQVXY0QWpuVER2M2p3YWt2bU9lUVZXUUNUcExRQkNrSjQxbExOV3FDdmxoS3IvWFp6eGVTSnFJTUFGQVYwCkJheUtLcXYwaEM3WGxWbnBZME9PUnE4VnJhbmhqWlJBb3JxWXZqRW56NEVjM0dUcmdlckxzQVJvcnhXQW4wSFIKVWFtZGZxWXliWjBGb0xJTHFBZE84YzlaM25jK01DelhZTTFMbzRHZUJxR1JmbzFVeXlja3lHK3o3cEFnbmFENgpSbnVZUTg4YXdLb09zT2xjVmtsbFZzaVRhcGNMRURVQktXRURCaC81ZGE3ZjJZdGVFOHJzQzRuWGxXbjhqckRaCk9UVUZPOWVhWVpTcDJ1S21LZ25ZVmxQYXpBR3ROS1lPT0JnMmoxeGswMEVGMEtYMEFOVlRYZE9pQSszMmN5ZVMKMi93PQotLS0tLUVORCBDRVJUSUZJQ0FURS0tLS0tCg==
    tls.key: LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlKS2dJQkFBS0NBZ0VBdkhrdWhyK0JCSXdEclNjY1BPZlRqdUg4MzlzTzdmZHZsbkFWTENaN0l3Nk5IbDJVCnFON3FCcG1kMFRvSm1wWlFEendkNm1GVjFiZytYcmVXWjdHemk4QmkxQ09aK0IzZFk1clFJek8yaTRhWU9HR08KdllITmIwL3pnYkExaDdobWFaMzdZc291aW9mbnZvQU5KZTd6QjA4Y3NUVUljZVB4Q0NjSXFKTkNTY09VOGpFTQpIVnduWXRId0tLajF2b1VCTWZpaVpOdlNDczd1SjRRZ01mbnl6K0p5a0tvbURUOWNHSGtucFg2eXVYOFhPOU5yCjEvRE1HdGt6SUMrSTJjaUM0aEJVdHhCZVBWY3FWOHJ0ektmYjZLcS84eVc4Vms2dW5CK05KMEJNTVhuUVNqbHYKRzZQY3BLRG9XQnRGZUFMM2xHdmpiUGIzclk0VjA4SVZ5Zmk2RFYvZDdNYmwyVTFJQkhDSnJvdjlGRmVFMnY4eApmSTNiem92ZlJYY2ZyczNJRmlPKzI1a1NmaXFOd242ZENoeTkwc0dOVlZNS0NrUG5vWW1FeXZKRkdrc3Y0NTJ0ClFPT1o4QldqQUNCUTJlcGN6MU1lUVBtS21xZjNBR3BQNzhMZGxLQmF6R3Z6UW16TDFFdHVjNjJHdlhPdkJVOXcKRzNmVyswNi9MZHFraVBlOE9PVTFWR0FaTlhQc1FCb0pma3F0ODN6eVNCbjRkUVhGWnFlWkgxVHhRaTZEcDFpbgpFeE13TTZTb2NTdlBwZGNLOGJveDRtNDh2R0xYMkU2R3czT2tIQ21TbzRKU3B4MmJ2amppM1Y4WkJCYU1IdldtCnBWRUs0Tld4bnVPUXE5UWpUWlRzVmh2cWp0Sm4xMXg4ckJYYnZSV2UrTjZzekNTOG5zeTI5bVArYW9FQ0F3RUEKQVFLQ0FnRUFvYUNpZjdmMjRubFlKY09tZWF5dFJwa1NqTDZGSFJuV3ZnSThoZkl5SXl3MVpOY0h4NUh5eTlvcwo5dUo0bmZOTmtPTVRISTZBVjVsN0V5c0pkcjl6bytOR1hYcHliYzdlcnE1eTA5MWpMR0F1Wmh0emw1eWJHbHhNCkRPbVozbHdLcDRSdHNwaUVOUlM3YmlqT0hidSsrb09qcld3M1k4UUFUZWQ3aTJWTnNZaGlVUmd5dFhMejY5RHgKelV5b0FjeDU2K3EzQ1J0aUV4YkdNV2tqV3Zob2ZGSkx3VGZKRGc5SjRVcjA3djJxTTEyRUJUQVlDY1ZjbzZHawpNSFBUUGtDdnpVSUlCRDJyTTV0dW1uOVNVdkdZcXZ6VFE2Y1d6a1VIaEtlaUd3a096bGNTZ3JTaVRlZkdMZ0EzCmdHZFN1Y3FCbXV5eXloMDQ1Y00xZ0xXdWpkZ1paQ2N6MTcxa2RDa3VPL2J2NDdoWkR0dXovVFdWWkhtbzd5TUEKYkI3TldPUVByNzFIUGtLUzh2ME11Y2JESHhqMUR0MEc4K05LSXV3N01nR2dQUldDQkR3OUh3cHZtVmdUZDNBTQphQURBeDV1TE1iQ3NZMEVNMGNmQUVVWXF1S05OdlA0Z0dPU3F3ME00Q2VGcjFITHBhM1NYTjF5a2grTXlKQVpwCnJ6cDBYY24zbytwcTN6UHd2Nk5wYkdDeEN2MzNkaU9MTTJtQmxBeXpGMHk3TVZvTnRVOFd6bFZYMzdWMjJPUEsKWk1FTlR5cGR5aTZLSDBBWVhwR2tNWXBZcDdCUm5UcWNsdFJjZ1FTckt2bmM1aTZqNDAwTVFXNEcxa2pPdlNWVQpmYWVJcG1Ca3V1d3JqR0xIWFE3ZGtKOE5TajBqSEVEMWFZUXJxZXFTQW9INVVTbVh5MGtDZ2dFQkFQaVArV2liClZPbG1Wc0NhWE5Mb3hYZXRkdEhkWXVmcStXYUtGTnRKNXZCNW5waTFqZ1R6UjNIay9FMlRvYU9jWW40M3hGS0YKbHdqK0xBc05wVDdBMkpLTERBRUZhTmV2SnVSZ29saXVSZ29XNXBIQSsvOVo5RkJON1ZsOC9sdERuSjZHRk9IRQpHeFludlk1U3piRkkwQ2dZejJwTnFXZktXOUlsb3J1cHg2cW1MalNKZnVSRFVCZll1dVhXTEZOY0wzRldDUmZkClhNY3JQbno5UzVhZmduVlJHS0V6MVlQZDdQMVEwTkhNRU8zNWxvMkJ3L2ErWk5rWjRJS29CbFA4SVVQZHI5blkKL1R3ZTdSR0dkUGY5VFVTUXlEbXBSdlFqWXp1NCtabmdkQ0pDMDJsOXZadnltOENUMlR4VklPaUl0RGptcGNlaQpwOFlNUTRUWnBlVUdROHNDZ2dFQkFNSWM2cGI3VVI3cXhpMittdWNKSkpLOVYzaDNDNzNXeGozKzI4TUNyMjhsClU3N2J6MUNjZ1dvSVBrRW9TRkxaaG1pMm9SYlQ0Uk9vREZDN2JHZXl2d2N4ZDZpS2tMNTgwa1NudHYwZHhUM2QKazI2RWhsWEJHQlpWVnY5MTJuY3lMN1RQWDdUeXRZdXFFYTlqd1N6ZkpSVzNYd0pWSStqR3B4VDVrdFBTNm54agpSdDdZb1NiM2p5MnFRNjh0ejJENW5mT3ViemNSSExkZVFqaktiS1BTbURFSHBKYktOWFI0d1VmS2NqK2FsREUwCm0vMmRmOGRjMHNBdUQ2S0FMVVc2NHFlUmdlRUllOXhpbDBoSStkcmxYNDk0dzFlby9Zc2lBUnp3TCtWMWN3cXQKRXBnUkN1a3NBNHh2eTA2bS9KT0tuaE1TWCsySnlDWDRhN3ZEUHQwdU9XTUNnZ0VCQUl1RnJYY2xjZVZOZDdiSApMd0dJZllkdkREcERMY2lHb2hZSHZpdFZjVmRjdlVSMDdOSWtpTjhLclFFU3RIRzFUNmdQdjVpZXVpZm5IR3ZiCjdmeXFuU2FzL0VENmUxNU9SK043eHNWR2xiUUdKTWg5N2pYb2xYWWFOL2U2Yk1CbjFGczdZaTlVTit3WXhKTkcKTVlXcEhJYlZYbUFLVmVRWHQ3RGZSVmhYdGVjNVBzaG93Wng1bUZTNmFEYXBJTnB0N1llTnhxN3BwN0Y0dWF2SgpOb3ZHMzZEZ3M1V1JGZkhlT2EvN2xDdWZnNFZCUzF3RkVpM0hzNjRWazJ0ank2R0s3bFU4OC8reGlId2QwKzY1CmJhRGlRMlFRYlFQSTNEWWdRd3g4Q1VkeHNWNmw2aXZWMC8vY2o4YnFkczhoN2NYNUxraWVWMElYTUZ1LytJcHkKN1djQVBEOENnZ0VCQUxSTi9jM09sWlJkU1VZMmRWWkRWTmlFelpvVklpL3RMdWxwTVNLYi9POEZ3aHRYdStOSgo3Si9jRmsrWnBreG14NFcrbGpWSkRCbWhFQWR4Z0lsMkxDRDNYd21MNUZVOFJtZ0ZUV0VoNVJQSkhHZ2M2MWIrCmJHeGFTdHd4MFlMRWVESEFLa3MrNDBsZTZOeDhrWFFudGgvTTI1Q2tHeDNlWUZhSVdFMHY3aVVxWmlzYkY5M0YKT0JhWHdCVVpQVGI3eGk4U2lUV2lUSVU3SmRId25TY3l0N0ZiUXhQWnNmdUZLeXVQTGI1TXpIaEVRTjA4RGZQVwpFZUQzS0FpdWZONzNjQTlzaGpMTUdaa2xieFp5eXJyOE1sNW5NelBhd2VBWjd1UzlhZy8rbjZSOERQaDVaQ1FnCmdROVN6SXM3YXdOMVQ4MnhWSytsT3VlaU1CZ1JqUFFRT3JjQ2dnRUFlTEU5NFVuZnZsUXN1eVMya0twUmI1aGYKY2p1M2pQQzJNNFpLNUJEb0NuQXFpalQ3UDZRRENsRlVObUErcnZmVEZuUllBb0tZQlk3NlJOcGttWUhWdFdlKwovZjhqOHFtTE9rYm0xbFNPbnh1YzJXazdEYWg0WUVyRW82QkN1b2UwZXYyWjV3TTJLUnFLeDBxNTB3L0M5bzM4ClNKekNvNE9LN0tHa2JCRVBNc1hVVHFwaFJmWnJDaEJHS2I5dkIvK0sxS1JjbXhrZ25IdElwMDFWclB1NE9qWUsKbDJhVVVoY1krbUpQazRSMnhTQWUxODVVTVFKWVc1dUhGcmx4T0o0OWNCeW0zUTZ3YWJZcldoSUxzdk5XajNXcAphSUxHR21FalNGYjdCYkRjbFlGMlozRFRibWZuNlFzMzhGOTBTdUJsZWwzUTFMVVpFU1YxQmw1aHhXd3ptQT09Ci0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0tCg==
  kind: Secret
  metadata:
    creationTimestamp: "2020-01-09T12:21:25Z"
    generateName: sealed-secrets-key
    labels:
      sealedsecrets.bitnami.com/sealed-secrets-key: active
    name: sealed-secrets-keygfvx8
    namespace: kube-system
    resourceVersion: "451323"
    selfLink: /api/v1/namespaces/kube-system/secrets/sealed-secrets-keygfvx8
    uid: 16986154-0017-4466-8f76-a0666a3d49af
  type: kubernetes.io/tls
kind: List
metadata:
  resourceVersion: ""
  selfLink: ""
"""

CRON_JOB_WITH_EXTRA_FIELDS = """
apiVersion: batch/v1beta1
kind: CronJob
metadata:
  name: test-cronjob
spec:
  schedule: '* * * * *'
  jobTemplate:
    spec:
      replicas: 1
      template:
        metadata:
          labels:
            app: test-cronjob
        spec:
          containers:
            - name: test-cronjob
              imagePullPolicy: IfNotPresent
              image: imagined.registry.tld/myproj-service-test-cronjob:latest
"""


def test_kubeval(clean_test_settings):
    kubeval()


def test_kubeval_strict_mode(clean_test_settings):
    kube_dir = TEST_ENV_PATH / "overrides" / "services" / "kube"
    kube_dir.mkdir(parents=True)
    with open(kube_dir / "cron.yaml", mode="w", encoding="utf-8") as f:
        f.write(CRON_JOB_WITH_EXTRA_FIELDS)
    with pytest.raises(subprocess.CalledProcessError):
        kubeval()


def test_base64_encode_decode_secrets():
    encoded = base64_encode_secrets(BASE64_DECODED_SECRETS)
    decoded = base64_decode_secrets(encoded)
    re_encoded = base64_encode_secrets(decoded)
    re_decoded = base64_decode_secrets(re_encoded)
    assert encoded == re_encoded
    assert decoded == re_decoded


def test_get_master_key(clean_test_settings, monkeypatch):
    TEST_ENV_PATH.mkdir(parents=True)
    TEST_ENV_SETTINGS.write_text(TEST_SETTINGS)

    assert TEST_ENV_MASTER_KEY.exists() is False

    def mock_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args, returncode=0, stdout=MASTER_KEY.encode(encoding="utf-8")
        )

    monkeypatch.setattr("subprocess.run", mock_run)

    get_master_key(TEST_ENV)
    assert TEST_ENV_MASTER_KEY.exists()
    assert TEST_ENV_MASTER_KEY.read_text(encoding="utf-8") == MASTER_KEY


def test_seal_unseal_secrets(clean_test_settings):
    yaml = YAML()
    original_decoded_secrets = yaml.load(BASE64_DECODED_SECRETS)
    assert original_decoded_secrets["kind"] == "Secret"

    TEST_ENV_PATH.mkdir(parents=True)
    TEST_ENV_SETTINGS.write_text(TEST_SETTINGS)
    TEST_ENV_MASTER_KEY.write_text(MASTER_KEY)
    TEST_ENV_SECRETS_PEM.write_text(SECRETS_PEM)
    TEST_ENV_SECRETS_PATH.mkdir()
    TEST_ENV_UNSEALED_SECRETS_PATH.write_text(BASE64_DECODED_SECRETS, encoding="utf-8")

    seal_secrets(TEST_ENV)
    TEST_ENV_UNSEALED_SECRETS_PATH.unlink()
    assert TEST_ENV_SEALED_SECRETS_PATH.exists()
    sealed_secrets = yaml.load(TEST_ENV_SEALED_SECRETS_PATH)
    assert sealed_secrets["kind"] == "SealedSecret"

    unseal_secrets(TEST_ENV)
    TEST_ENV_SEALED_SECRETS_PATH.unlink()
    assert TEST_ENV_UNSEALED_SECRETS_PATH.exists()

    new_decoded_secrets = yaml.load(TEST_ENV_UNSEALED_SECRETS_PATH)
    assert new_decoded_secrets["kind"] == "Secret"
    assert new_decoded_secrets["data"] == original_decoded_secrets["data"]


def test_update_from_templates(clean_test_settings, clean_test_component):
    TEST_ENV_PATH.mkdir(parents=True)
    TEST_ENV_SETTINGS.write_text(TEST_SETTINGS_WITH_VARIABLES)

    TEST_COMPONENT_OVERRIDE_TEMPLATE_PATH.parent.mkdir(parents=True)
    TEST_COMPONENT_OVERRIDE_TEMPLATE_PATH.write_text(TEST_COMPONENT_OVERRIDE_TEMPLATE)
    original_path_string = TEST_COMPONENT_OVERRIDE_TEMPLATE_PATH.as_posix()

    # Check override file is generated correctly
    assert TEST_COMPONENT_RENDERED_OVERRIDE_PATH.exists() is False
    update_from_templates()
    assert TEST_COMPONENT_RENDERED_OVERRIDE_PATH.exists() is True
    rendered_content = TEST_COMPONENT_RENDERED_OVERRIDE_PATH.read_text()
    expected_content = TEMPLATE_HEADER.format(file=original_path_string)
    expected_content += TEST_COMPONENT_RENDERED_OVERRIDE
    assert rendered_content == expected_content

    # Check override file gets deleted if original file is deleted
    TEST_COMPONENT_OVERRIDE_TEMPLATE_PATH.unlink()
    assert TEST_COMPONENT_RENDERED_OVERRIDE_PATH.exists() is True
    update_from_templates()
    assert TEST_COMPONENT_RENDERED_OVERRIDE_PATH.exists() is False

    # Re-create the template file and rendered the override file
    TEST_COMPONENT_OVERRIDE_TEMPLATE_PATH.write_text(TEST_COMPONENT_OVERRIDE_TEMPLATE)
    update_from_templates()
    assert TEST_COMPONENT_RENDERED_OVERRIDE_PATH.exists() is True

    # Remove the component from settings and check rendered file is removed
    settings_without_components = "".join(
        [
            line if not line.startswith("COMPONENTS = [") else "COMPONENTS = []\n"
            for line in TEST_SETTINGS_WITH_VARIABLES.splitlines(keepends=True)
        ]
    )
    TEST_ENV_SETTINGS.write_text(settings_without_components)
    update_from_templates()
    assert TEST_COMPONENT_RENDERED_OVERRIDE_PATH.exists() is False
