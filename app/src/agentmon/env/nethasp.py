"""Генерация nethasp.ini для доступа к сетевому серверу лицензирования 1С.

При client-server + сетевых лицензиях контейнеру/удалённому хосту достаточно
указать адрес NETHASP-сервера — файл кладётся в каталог профиля платформы проекта
(conf/nethasp.ini). Пустой адрес → файл не пишем (платформа ищет лицензию штатно).
"""


def render_nethasp_ini(server_addr: str) -> str:
    return (
        "[NH_COMMON]\n"
        "NH_TCPIP = Enabled\n"
        "\n"
        "[NH_TCPIP]\n"
        f"NH_SERVER_ADDR = {server_addr}\n"
        "NH_TCPIP_METHOD = TCP\n"
        "NH_USE_BROADCAST = Disabled\n"
        "\n"
        "[NH_SERVER]\n"
        f"NH_SERVER_ADDR = {server_addr}\n"
    )


def _target_home(prov) -> str | None:
    """Домашний каталог пользователя на цели (для ~/.1cv8/conf)."""
    try:
        r = prov.run(["sh", "-c", 'printf %s "$HOME"'])
    except Exception:
        return None
    home = (getattr(r, "stdout", "") or "").strip()
    if getattr(r, "returncode", 1) == 0 and home.startswith("/"):
        return home
    return None


def deploy_nethasp(prov, config, *, home: str | None = None) -> None:
    """Записать nethasp.ini в каталоги, где его ищет платформа.

    Одного <project>/conf мало: 1С читает conf рядом с бинарником платформы и
    ~/.1cv8/conf пользователя. Пишем во все доступные места (best-effort —
    отсутствие прав на домашний каталог не должно валить создание проекта).
    """
    server = (config.license_server or "").strip()
    if not server:
        return
    content = render_nethasp_ini(server)
    targets = [f"{config.project_dir}/conf/nethasp.ini"]
    platform_dir = (getattr(config, "platform_dir", "") or "").rstrip("/")
    if platform_dir:
        targets.append(f"{platform_dir}/conf/nethasp.ini")
    home = home if home is not None else _target_home(prov)
    if home:
        targets.append(f"{home.rstrip('/')}/.1cv8/conf/nethasp.ini")
    for path in targets:
        try:
            prov.write_text(path, content)
        except Exception:
            continue          # лицензионный файл — best-effort
