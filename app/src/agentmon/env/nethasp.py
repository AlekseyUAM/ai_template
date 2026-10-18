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


def deploy_nethasp(prov, config) -> None:
    server = (config.license_server or "").strip()
    if not server:
        return
    prov.write_text(f"{config.project_dir}/conf/nethasp.ini",
                    render_nethasp_ini(server))
