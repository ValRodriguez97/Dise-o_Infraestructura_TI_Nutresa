# Documentación Técnica — Infraestructura de TI Grupo Nutresa S.A.

**Curso:** Administración de Infraestructura de TI · Universidad del Quindío · Facultad de Ingeniería de Sistemas y Computación · Semestre 2026-1


## Índice

| # | Sección | 
|---|---|
| 1 | Infraestructura base: virtualización con Multipass y red *bridged* 
| 2 | Servicio NTP con Chrony 
| 3 | Servicio NFSv4 
| 4 | Servicio NIS 
| 5 | Servicio Samba 
| 6 | Servicio CUPS 
| 7 | Dokploy, Traefik, dominio y SSL/TLS 
| 8 | PostgreSQL en Dokploy 
| 9 | Sitio web (Nginx) y Backend API desde Git 

**Nodos implementados** (los valores de `analisis.md` proyectaban `192.168.1.10`; la implementación real quedó así):

| Nodo | Sistema | Recursos | IP | Rol |
|---|---|---|---|---|
| `nutresa-server` | Ubuntu 24.04.5 LTS (Multipass) | 2 vCPU · 4 GB RAM · 40 GB disco | `192.168.1.34/24` (`eth1`) | Servidor de servicios |
| `nutresa-cliente` | Ubuntu 24.04.5 LTS (Multipass) | 2 vCPU · 2 GB RAM · 20 GB disco | `192.168.1.35/24` | Cliente Linux de pruebas |
| `host-windows` | Windows 11 | — | `192.168.1.31/24` | Anfitrión de las VM y cliente Windows |

---


# Sección 1. Infraestructura base: virtualización Multipass y red *bridged*

**Objetivo.** Tener una máquina virtual Ubuntu Server 24.04 LTS con al menos 2 vCPU, 4 GB de RAM y 40 GB de disco, conectada en modo puente (*bridged*) a la red Wi-Fi local, para que los clientes de la red `192.168.1.0/24` puedan alcanzar sus servicios. Se crea además una segunda VM cliente para probar NTP, NFS, NIS, Samba y CUPS.

**Resumen de lo realizado**

1. Crear `nutresa-server` con Multipass.
2. Actualizar el sistema e instalar herramientas de administración.
3. Crear el switch virtual externo `Nutresa-External` en Hyper-V (puente hacia el Wi-Fi).
4. Asociar la VM al switch y obtener una IP dentro de `192.168.1.0/24`.
5. Crear `nutresa-cliente` y comprobar la comunicación entre ambos nodos.

## 1.1 Crear la máquina virtual del servidor

En **PowerShell del host Windows**:

```powershell
multipass launch 24.04 --name nutresa-server --cpus 2 --memory 4G --disk 40G
multipass list
multipass info nutresa-server
```

**Verificación.** `multipass info` debe mostrar `State: Running`, `Release: Ubuntu 24.04.5 LTS`, `CPU(s): 2`, disco ≈ 38,7 GiB y memoria ≈ 3,8 GiB.

![Creación de nutresa-server](capturas/01a_crear_vm_launch_info.png)

*Captura 01a — `capturas/01a_crear_vm_launch_info.png`: creación de la VM con `multipass launch`, listado con `multipass list` e información con `multipass info`.*

![Acceso a la VM](capturas/01b_acceso_vm_multipass_shell.png)

*Captura 01b — `capturas/01b_acceso_vm_multipass_shell.png`: ingreso a la VM con `multipass shell` y mensaje de bienvenida de Ubuntu 24.04.5 LTS.*

Se ingresa a la VM con:

```powershell
multipass shell nutresa-server
```

## 1.2 Actualizar el sistema e instalar herramientas de administración

Dentro de `nutresa-server`:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl wget git nano vim net-tools iproute2 dnsutils iputils-ping traceroute chrony openssh-server ufw
```

Estas herramientas permiten administrar el servidor (`nano`, `vim`), probar la conectividad (`ping`, `traceroute`, `dnsutils`), consultar la red (`ip`, `net-tools`), acceder de forma remota (`openssh-server`), sincronizar la hora (`chrony`) y gestionar el firewall (`ufw`).



![Actualización del sistema](capturas/02a_apt_update_upgrade.png)

*Captura 02a — `capturas/02a_apt_update_upgrade.png`: actualización del sistema con `apt update` y `apt upgrade`.*

![Herramientas base](capturas/02b_instalar_herramientas_base.png)

*Captura 02b — `capturas/02b_instalar_herramientas_base.png`: instalación de las herramientas de administración.*

### Nombre del servidor, salida a internet y SSH

Se fija el nombre del equipo, se verifica la red y la salida a internet, y se activa el acceso remoto por SSH:

```bash
sudo hostnamectl set-hostname nutresa-server
hostnamectl
ip -br addr
ip route
ping -c 4 8.8.8.8
ping -c 4 google.com
sudo systemctl enable --now ssh
sudo systemctl status ssh --no-pager
```

**Verificación.** `hostnamectl` muestra `Static hostname: nutresa-server`; ambos `ping` responden con 0 % de pérdida (prueba de salida a internet y de resolución DNS); `ssh` queda `enabled` y `active (running)`.

![Nombre del servidor, IP y rutas](capturas/02c_hostname_ip_ruta.png)

*Captura 02c — `capturas/02c_hostname_ip_ruta.png`: nombre del servidor (`hostnamectl set-hostname`), dirección IP y rutas (`ip -br addr`, `ip route`).*

![Salida a internet](capturas/02d_ping_internet.png)

*Captura 02d — `capturas/02d_ping_internet.png`: comprobación de salida a internet con `ping` a `8.8.8.8` y a `google.com`.*

![SSH activo](capturas/02e_ssh_activo.png)

*Captura 02e — `capturas/02e_ssh_activo.png`: activación del servicio SSH y verificación de su estado.*

## 1.3 Red: crear el switch externo (modo *bridged*)

Por defecto Multipass en Hyper-V conecta la VM al **Default Switch** (red NAT interna, en este caso `172.x.x.x`), que **no** pertenece a la red Wi-Fi `192.168.1.0/24`. Para que la VM sea accesible desde la red local se crea un switch virtual **externo** ligado al adaptador Wi-Fi.

1. Listar las redes que conoce Multipass y los adaptadores del host:

   ```powershell
   multipass networks
   Get-NetAdapter | Format-Table Name, InterfaceDescription, Status
   ```

   Solo aparecen `Default Switch` y `WSL (Hyper-V firewall)`. El adaptador físico a usar es `Wi-Fi` (Realtek RTL8852AE WiFi 6).

2. Intentar consultar los switches existentes:

   ```powershell
   Get-VMSwitch | Format-Table Name, SwitchType, NetAdapterInterfaceDescription
   ```

   ![Error de permisos](capturas/03a_multipass_networks_error_permisos.png)

   *Captura 03a — `capturas/03a_multipass_networks_error_permisos.png`: `multipass networks`, `Get-NetAdapter` y el error de `Get-VMSwitch` por falta de permisos (ver Problema 1.A).*

   ![IP del host](capturas/03b_ip_host_get_netipconfiguration.png)

   *Captura 03b — `capturas/03b_ip_host_get_netipconfiguration.png`: `Get-NetIPConfiguration` en el host: las interfaces virtuales usan direcciones `172.x.x.x`, fuera de la red Wi-Fi.*

3. Crear el switch externo (PowerShell **como administrador**):

   ```powershell
   New-VMSwitch -Name "Nutresa-External" -NetAdapterName "Wi-Fi" -AllowManagementOS $true
   ```

   `-AllowManagementOS $true` mantiene el acceso a internet del host a través del mismo adaptador.

   ![Creación del switch externo](capturas/04a_crear_switch_Nutresa-External.png)

   *Captura 04a — `capturas/04a_crear_switch_Nutresa-External.png`: creación del switch externo `Nutresa-External` con `New-VMSwitch`.*

   ![Comprobación del switch](capturas/04b_comprobar_switch_externo.png)

   *Captura 04b — `capturas/04b_comprobar_switch_externo.png`: comprobación con `Get-VMSwitch` y `multipass networks`: el switch aparece como `External`.*

   ![Verificación del switch (segundo intento)](capturas/04c_verificar_switch_segundo_intento.png)

   *Captura 04c — `capturas/04c_verificar_switch_segundo_intento.png`: verificación del switch y de los adaptadores con `Get-VMSwitch` y `Get-NetAdapter` (segundo intento).*

4. Comprobar:

   ```powershell
   Get-VMSwitch | Format-Table Name, SwitchType, NetAdapterInterfaceDescription
   ```

   Debe listar `Nutresa-External — External — Realtek RTL8852AE WiFi 6 802.11ax PCIe Adapter` junto a `Default Switch — Internal`.

## 1.4 Asociar la VM al switch y obtener IP en `192.168.1.0/24`

Con la VM detenida se le asigna la red puente y se vuelve a iniciar:

```powershell
multipass stop nutresa-server
multipass set local.bridged-network=Nutresa-External
multipass set local.nutresa-server.bridged=true
multipass start nutresa-server
multipass list
multipass shell nutresa-server
```

Dentro de la VM se verifica la interfaz nueva `eth1`:

```bash
ip -br addr
ip route
```

Obtener una IP correcta en la red local tomó dos intentos (resumen en la sección 1.9).

### Intento 1: la VM toma la misma IP del host

Al arrancar con el switch externo, `eth1` recibió `192.168.1.31`, que es **la misma IP del host Windows**. Dos equipos con la misma dirección generan un conflicto, así que esa IP no se puede usar (Problema 1.B).

![Asociar el switch a la VM](capturas/05a_asociar_switch_bridged.png)

*Captura 05a — `capturas/05a_asociar_switch_bridged.png`: la VM se detiene, se asocia a la red puente y se reinicia (`multipass list` muestra `192.168.1.31`).*

![Conflicto de IP con el host](capturas/05b_conflicto_ip_con_host_windows.png)

*Captura 05b — `capturas/05b_conflicto_ip_con_host_windows.png`: `ip -br addr` dentro de la VM: `eth1` tomó `192.168.1.31`, igual a la IP del host Windows (ver Problema 1.B).*

### Intento 2: asignar manualmente una IP libre

Se comprobó con `arping` que `192.168.1.10` (la IP proyectada en `analisis.md`) estaba libre (`Received 0 response(s)`) y se asignó a `eth1` a mano:

```bash
sudo arping -D -I eth1 -c 4 192.168.1.10      # 0 respuestas => la IP está libre
sudo ip -4 addr flush dev eth1
sudo ip addr add 192.168.1.10/24 dev eth1
sudo ip link set eth1 up
ip -4 -br address
```

![Asignación de IP a eth1](capturas/06_asignacion_ip_eth1.png)

*Captura 06 — `capturas/06_asignacion_ip_eth1.png`: comprobación con `arping` y asignación manual de `192.168.1.10/24` en `eth1`.*

Esta asignación **no es persistente**: se pierde al reiniciar la VM, por lo que no quedó como configuración definitiva.

### Resultado final

Con el switch externo verificado, el servidor quedó con estas direcciones (`ip -br addr`):

```text
lo      UNKNOWN   127.0.0.1/8 ::1/128
eth0    UP        172.31.38.240/20          # red interna de Hyper-V (Default Switch)
eth1    UP        192.168.1.34/24           # red Wi-Fi local (switch Nutresa-External)
```

`eth1` tiene `192.168.1.34/24` con puerta de enlace `192.168.1.1`. La IP `192.168.1.34` es la dirección de servicio de `nutresa-server` en todo el proyecto.

**IP de servicio fija.** Como `eth1` recibe su dirección por DHCP, esta puede cambiar cuando la VM cambia de red (ver Problema 1.E). Para que `192.168.1.34` no se pierda, se configuró como **dirección adicional** en `eth1`, manteniendo el DHCP activo. Se revisa el archivo de Netplan y las direcciones de la interfaz con:

```bash
sudo cat /etc/netplan/*.yaml
ip -4 addr show eth1
```

Con esto, si el DHCP entrega otra dirección, el servidor sigue respondiendo en `192.168.1.34` y los servicios (NTP, NFS, etc.) no dejan de funcionar. Los pasos detallados de esa configuración son los siguientes.

### Configuración detallada de la IP fija en Netplan

**Paso 1 — Revisar la red actual de la VM.** Se revisan las interfaces y las rutas para identificar cuál es la red local: `eth0` es la red interna de Hyper-V y `eth1` es la red Wi-Fi `192.168.1.x`:

```bash
ip -br addr
ip route
ls -l /etc/netplan/
sudo cat /etc/netplan/*.yaml
```

*(Captura pendiente.)*

**Paso 2 — Comprobar que `192.168.1.34` está libre.** Antes de usarla se probó con un `ping` desde Windows:

```powershell
ping 192.168.1.34
```

El ping devolvió «Respuesta desde 192.168.1.14: Host de destino inaccesible», es decir, la dirección estaba libre.

*(Captura pendiente.)*

**Paso 3 — Crear la configuración de Netplan.** No se modificó el archivo original (`50-cloud-init.yaml`, generado por cloud-init): se hizo una copia de seguridad y se creó un archivo adicional que solo añade la IP:

```bash
sudo mkdir -p /root/backup-red
sudo cp -a /etc/netplan/50-cloud-init.yaml /root/backup-red/50-cloud-init.yaml.bak
sudo nano /etc/netplan/60-nutresa.yaml
```

*(Captura pendiente.)*

Contenido de `60-nutresa.yaml`:

```yaml
network:
  version: 2
  ethernets:
    extra0:
      addresses:
        - 192.168.1.34/24
```

*(Captura pendiente.)*

Se ajustan permisos y se valida la configuración:

```bash
sudo chown root:root /etc/netplan/60-nutresa.yaml
sudo chmod 600 /etc/netplan/60-nutresa.yaml
sudo netplan generate
sudo netplan get
```

*(Captura pendiente.)*

**Paso 4 — Aplicar la configuración de forma segura.** `netplan try` aplica el cambio y lo revierte automáticamente a los 120 segundos si no se confirma:

```bash
sudo netplan try --timeout 120
```

Se confirma con Enter y luego se verifica dentro de la VM:

```bash
ip -br addr
ip route
sudo docker node ls
```

Y desde Windows:

```powershell
ping 192.168.1.34
arp -a | findstr 192.168.1.34
```

*(Capturas pendientes: verificación con `netplan try` y con `ping`/`arp -a` desde Windows.)*

## 1.5 Crear el nodo cliente

En PowerShell:

```powershell
multipass launch 24.04 --name nutresa-cliente --cpus 2 --memory 2G --disk 20G
multipass shell nutresa-cliente
```

Dentro del cliente se actualiza e instalan las herramientas de cliente de todos los servicios del proyecto:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y openssh-client nfs-common nis rpcbind samba-client cups-client chrony
```

![Creación del cliente](capturas/07a_crear_nutresa_cliente.png)

*Captura 07a — `capturas/07a_crear_nutresa_cliente.png`: creación de `nutresa-cliente` y primer acceso.*

![Herramientas del cliente](capturas/07b_herramientas_cliente.png)

*Captura 07b — `capturas/07b_herramientas_cliente.png`: actualización del cliente e instalación de sus herramientas.*

Al crearse, la VM recibe una IP de la red interna (NAT) del hipervisor: `10.0.2.15` en la interfaz `enp0s3`, que **no pertenece** a la red local y desde la que no se alcanza el servidor. Por eso, después de crearla, se le asignó una **nueva IP dentro del rango de la red local**, `192.168.1.35/24`, que es la que usa el cliente en todas las pruebas (visible como `clientaddr=192.168.1.35` en el montaje NFS de la Sección 3). Las dos situaciones quedaron registradas en las capturas del cliente.

## 1.6 Verificar la comunicación entre nodos

Desde `nutresa-cliente`:

```bash
ping -c 4 192.168.1.34
```

**Resultado esperado y obtenido:** `4 packets transmitted, 4 received, 0% packet loss` (latencias entre ≈ 8 y 70 ms por el medio Wi-Fi).

![Ping cliente-servidor](capturas/08_ping_cliente_servidor.png)

*Captura 08 — `capturas/08_ping_cliente_servidor.png`: conectividad cliente → servidor.*

## 1.7 Lista de verificación de la Sección 1

| Verificación | Comando | Resultado esperado | Captura |
|---|---|---|---|
| VM con recursos correctos | `multipass info nutresa-server` | 2 CPU · 3,8 GiB · 38,7 GiB · Ubuntu 24.04.5 LTS | 01 |
| Herramientas instaladas | `dpkg -l chrony ufw openssh-server` | estado `ii` | 02 |
| Switch externo | `Get-VMSwitch` | `Nutresa-External` tipo `External` | 04 |
| IP en la red local | `ip -br addr` | `eth1 192.168.1.34/24` | 05, 06 |
| Cliente → servidor | `ping -c 4 192.168.1.34` | 0 % de pérdida | 08 |

## 1.8 Solución de problemas de la Sección 1

| # | Problema | Causa | Solución |
|---|---|---|---|
| 1.A | La VM obtenía `172.x.x.x`, fuera de la red Wi-Fi, y `Get-VMSwitch` fallaba con *"No dispone del permiso necesario"* (Captura 03). | Multipass usaba el *Default Switch* (NAT) y PowerShell se ejecutaba sin privilegios de administrador / sin pertenecer a *Hyper-V Administrators*. | Abrir PowerShell **como administrador** y crear el switch externo `Nutresa-External` (Captura 04). |
| 1.B | Tras asociar el switch, la VM tomó `192.168.1.31`, la **misma IP del host Windows** (Captura 05). | Conflicto de direccionamiento con la IP ya usada por el anfitrión. | Verificar con `arping -D` una IP libre y reasignar `eth1` (Captura 06); la VM quedó finalmente con `192.168.1.34/24`. |
| 1.C | Dos rutas por defecto (`eth0` métrica 100 y `eth1` métrica 200). | La VM tiene dos interfaces (Default Switch y puente). | No requiere acción: el tráfico a `192.168.1.0/24` sale por `eth1` (ruta de red directa); los servicios se anuncian siempre con `192.168.1.34`. |
| 1.D | `ping 192.168.1.10` desde el cliente devolvía respuestas duplicadas y datos erróneos (*wrong data byte*, *DUP!*). | `192.168.1.10` era la IP proyectada en `analisis.md` y ya no pertenece al servidor. | Usar `192.168.1.34`, que respondió con 0 % de pérdida (Captura 08). |
| 1.E | La IP de la VM cambiaba: al principio era `192.168.1.34` y después pasó a `192.168.1.11`. | `eth1` la recibe por DHCP y la VM se movió de red. | Se fijó `192.168.1.34` como dirección adicional en `eth1` (Netplan), manteniendo el DHCP; así, si la VM cambia de red, conserva conectividad en la IP de servicio. |
| 1.F | El cliente no alcanzaba al servidor: `ip route get 192.168.1.34` salía por `10.0.2.2` (NAT) y el montaje NFS fallaba con `Operation not permitted`. | La VM del cliente se crea con una IP de la red NAT (`10.0.2.15`), fuera de `192.168.1.0/24`. | Asignarle una IP dentro del rango de la red local (`192.168.1.35/24`) y repetir las pruebas (ver también 3.B). |

## 1.9 Registro de intentos

La red del servidor se resolvió en dos intentos:

| Intento | Fecha | Qué se hizo | Resultado |
|---|---|---|---|
| 1 | 8 de noviembre de 2026 | Se creó `nutresa-server` con el *Default Switch* de Hyper-V y se accedió, actualizó y configuró (capturas 01 a 02e). Se revisó la red del host (captura 03). | La VM quedó en `172.23.112.208`, fuera de `192.168.1.0/24`. Se creó el switch externo `Nutresa-External` (captura 04) y se asoció a la VM. |
| 1 (continuación) | 8 de noviembre de 2026 | Al asociar el switch, `eth1` tomó `192.168.1.31`, la misma IP del host (captura 05). Se probó una IP manual libre, `192.168.1.10` (captura 06). | Conflicto de IP; la asignación manual no es persistente. |
| 2 | 10 de noviembre de 2026 | Se verificó el switch externo (captura 04). El servidor mostró `eth0 172.31.38.240` (red interna) y `eth1 192.168.1.34/24` (red local). Se creó `nutresa-cliente` (captura 07) y se probó la comunicación (captura 08). | Configuración definitiva: IP de servicio `192.168.1.34`, fijada además como dirección adicional en `eth1`. |

---

# Sección 2. Servicio NTP con Chrony

**Objetivo.** Que `nutresa-server` sincronice su reloj con una fuente confiable de internet y actúe como **servidor NTP de la red local** (puerto `123/udp`), de modo que `nutresa-cliente` se sincronice contra `192.168.1.34`. La hora uniforme es necesaria para registros de auditoría, bitácoras, certificados SSL y autenticación.

**Decisión de diseño.** La guía del curso usa el paquete `ntp` (`ntpq -p`). En Ubuntu 24.04 el servicio estándar y mantenido es **Chrony**, que cumple la misma función (cliente y servidor NTP) y se verifica con `chronyc`. Los pasos de la guía se mantienen: instalar, configurar, habilitar y verificar.

| Parámetro | Valor |
|---|---|
| Servidor NTP | `nutresa-server` · `192.168.1.34` |
| Paquete / servicio | `chrony` (`chrony.service`) |
| Puerto | `123/udp` |
| Fuentes externas | `ntp.ubuntu.com` y `*.ubuntu.pool.ntp.org` (las de Ubuntu por defecto) |
| Clientes autorizados | `192.168.1.0/24` |
| Configuración | `codigo/chrony.conf` |

## 2.1 Servidor: instalar y habilitar Chrony

En `nutresa-server`:

```bash
sudo apt update
sudo apt install -y chrony
sudo systemctl enable --now chrony
sudo systemctl status chrony
```

**Verificación.** El servicio debe aparecer `enabled` y `Active: active (running)`; en el registro se ve la selección de fuente (`Selected source ... ntp.ubuntu.com`).

También se activó la sincronización del sistema:

```bash
timedatectl
sudo timedatectl set-ntp true
timedatectl status
```

Resultado: `Time zone: America/Bogota (-05, -0500)`, `System clock synchronized: yes`, `NTP service: active`.

## 2.2 Servidor: permitir que los clientes de la red local consulten la hora

Se edita el archivo de configuración:

```bash
sudo nano /etc/chrony/chrony.conf
```

Al final del archivo se agrega:

```text
# Servidor NTP de Nutresa
allow 192.168.1.0/24
# Permitir sincronizacion de clientes de la red local
```

La directiva `allow` autoriza a los equipos de `192.168.1.0/24` a usar este servidor como fuente de hora (sin ella, Chrony solo actúa como cliente). Se reinicia el servicio:

```bash
sudo systemctl restart chrony
```

## 2.3 Servidor: verificar fuentes y estado de sincronización

```bash
chronyc sources -v
chronyc tracking
```

- `chronyc sources -v`: lista las fuentes; la marcada `^*` es la mejor fuente actual (`alphyn.canonical.com`, estrato 2).
- `chronyc tracking`: muestra el estado. Valores obtenidos: `Reference ID : 5BBD5B9D (alphyn.canonical.com)`, `Stratum : 3`, `System time : 0.000137431 seconds fast of NTP time`, `Leap status : Normal`.

El servidor queda en **estrato 3**: toma la hora de una fuente de estrato 2 y la ofrece a los clientes.

![Paquetes básicos](capturas/09a_chrony_paquetes_basicos.png)

*Captura 09a — `capturas/09a_chrony_paquetes_basicos.png`: actualización del sistema e instalación de `chrony`.*

![Chrony activo](capturas/09b_chrony_servicio_activo.png)

*Captura 09b — `capturas/09b_chrony_servicio_activo.png`: activación del servicio `chrony` y verificación de su estado.*

![Fuentes de hora](capturas/09c_chrony_fuentes_servidor.png)

*Captura 09c — `capturas/09c_chrony_fuentes_servidor.png`: reinicio del servicio y fuentes de hora con `chronyc sources -v`.*

## 2.4 Servidor: abrir el puerto NTP en el firewall

```bash
sudo ufw allow from 192.168.1.0/24 to any port 123 proto udp
```

Salida: `Rules updated`. La regla permite `123/udp` únicamente desde la subred local.



![Chrony tracking](capturas/10a_chrony_tracking.png)

*Captura 10a — `capturas/10a_chrony_tracking.png`: estado de sincronización con `chronyc tracking` (estrato 3, `Leap status: Normal`).*

![Regla UFW 123/udp](capturas/10b_ufw_puerto_123.png)

*Captura 10b — `capturas/10b_ufw_puerto_123.png`: regla de firewall para `123/udp` desde `192.168.1.0/24`.*

## 2.5 Cliente: sincronizar contra el servidor local

En `nutresa-cliente`:

```bash
sudo timedatectl set-ntp true
sudo apt install -y chrony
sudo nano /etc/chrony/chrony.conf     # agregar la línea:  server 192.168.1.34 iburst
sudo systemctl enable --now chrony
sudo systemctl restart chrony
chronyc sources -v
chronyc tracking
```

**Resultado obtenido:**

```text
MS Name/IP address         Stratum Poll Reach LastRx Last sample
^* 192.168.1.34                  3   6    37     4    +52us[ +599us] +/-   71ms
```

`chronyc tracking` en el cliente: `Reference ID : C0A80122 (192.168.1.34)`, `Stratum : 4`, `System time : 0.000299279 seconds fast of NTP time`, `Leap status : Normal`. Es decir, el cliente se sincroniza con `192.168.1.34` (`C0A80122` es esa IP en hexadecimal) y queda un estrato por debajo del servidor.

![Configuración de Chrony en el cliente](capturas/11a_chrony_cliente_configuracion.png)

*Captura 11a — `capturas/11a_chrony_cliente_configuracion.png`: cliente: actualización, instalación de `chrony` y edición de `/etc/chrony/chrony.conf`.*

![Cliente sincronizado](capturas/11b_chrony_cliente_sincronizado.png)

*Captura 11b — `capturas/11b_chrony_cliente_sincronizado.png`: cliente: `chronyc sources -v` con `^* 192.168.1.34` como fuente seleccionada.*

## 2.6 Lista de verificación de la Sección 2

| Verificación | Comando | Resultado esperado | Captura |
|---|---|---|---|
| Servicio activo | `systemctl status chrony` | `active (running)` | 09 |
| Fuente externa elegida | `chronyc sources -v` (servidor) | una fuente `^*` | 09 |
| Servidor sincronizado | `chronyc tracking` (servidor) | `Stratum 3`, `Leap status: Normal` | 10 |
| Puerto abierto a la LAN | `sudo ufw status` / regla `123/udp` | `192.168.1.0/24` → `123/udp` | 10 |
| Cliente sincronizado con el servidor | `chronyc sources -v` (cliente) | `^* 192.168.1.34` | 11 |

## 2.7 Solución de problemas de la Sección 2

| # | Problema | Causa | Solución |
|---|---|---|---|
| 2.A | Dudas de que `chrony` y `systemd-timesyncd` compitan por la hora. | Ambos son clientes NTP. | Al instalar `chrony`, APT retira `systemd-timesyncd`; `timedatectl` sigue mostrando `NTP service: active` (ahora gestionado por Chrony). |
| 2.B | Tras reiniciar Chrony, algunas fuentes externas aparecen con `^?` (p. ej. `alphyn.canonical.com`). | Aún no acumulan suficientes muestras (`Reach 17` octal indica que apenas empiezan a responder). | No requiere acción: esperar uno o dos intervalos de sondeo (≈ 64 s) y repetir `chronyc sources -v`. La fuente local `192.168.1.34` ya aparece como `^*` (Captura 11). |
| 2.C | El cliente no consulta al servidor. | Falta `allow` en el servidor o el puerto `123/udp` está bloqueado. | Verificar `allow 192.168.1.0/24` en `/etc/chrony/chrony.conf`, reiniciar `chrony` y revisar la regla UFW `123/udp`. |

---

# Sección 3. Servicio NFSv4 (archivos compartidos para Linux)

**Objetivo.** Compartir el directorio corporativo `/srv/nfs/nutresa` del servidor con los clientes Linux de la red `192.168.1.0/24` mediante **NFSv4**, con acceso por grupo y montaje permanente en el cliente.

**Decisiones de diseño** (se mantienen los pasos de la guía; se endurece la configuración):

- **NFSv4** con `fsid=0`: toda la exportación viaja por un único puerto, `2049/tcp`.
- **`root_squash`** activo (la guía de ejemplo usa `no_root_squash`, que no es recomendable): el `root` remoto no tiene privilegios de `root` en el servidor.
- Acceso restringido a la subred `192.168.1.0/24`.
- Permisos por **grupo**: grupo `nutresa` con **GID 2000** igual en servidor y cliente, porque NFS identifica a los usuarios por UID/GID numéricos. El directorio usa `2770` (bit *setgid*), de modo que los archivos nuevos heredan el grupo `nutresa`.

| Parámetro | Valor |
|---|---|
| Servidor | `192.168.1.34` · paquete `nfs-kernel-server` |
| Directorio exportado | `/srv/nfs/nutresa` (`root:nutresa`, `2770`) |
| Grupo | `nutresa` · GID `2000` |
| Puerto | `2049/tcp` |
| Punto de montaje (cliente) | `/mnt/nutresa` |
| Configuración | `codigo/exports` |

## 3.1 Servidor: instalar y activar NFS

En `nutresa-server`:

```bash
sudo apt update
sudo apt install -y nfs-kernel-server
sudo systemctl enable --now nfs-kernel-server
sudo systemctl status nfs-kernel-server
```

**Verificación.** El servicio `nfs-server.service` aparece `enabled` y `active (exited)` (es normal: lanza procesos del kernel y termina). Mientras `/etc/exports` no existe, el log muestra `exportfs: can't open /etc/exports for reading` (ver Problema 3.A).

## 3.2 Servidor: crear el grupo y el directorio compartido

```bash
sudo groupadd -g 2000 nutresa
sudo mkdir -p /srv/nfs/nutresa
sudo chown root:nutresa /srv/nfs/nutresa
sudo chmod 2770 /srv/nfs/nutresa
ls -ld /srv/nfs/nutresa
```

Resultado: `drwxrws--- 2 root nutresa 4096 ... /srv/nfs/nutresa`.

El `2` de `2770` activa el bit **setgid** (la `s` en `rws`): los archivos y subdirectorios nuevos heredan el grupo `nutresa`. Solo `root` y los miembros del grupo pueden leer y escribir (`770`).

## 3.3 Servidor: configurar la exportación

```bash
sudo nano /etc/exports
```

Contenido (también en `codigo/exports`):

```text
/srv/nfs/nutresa 192.168.1.0/24(rw,sync,no_subtree_check,root_squash,fsid=0)
```

| Opción | Función |
|---|---|
| `rw` | Permite lectura y escritura |
| `sync` | Confirma las escrituras de forma sincronizada (más seguro ante fallos) |
| `no_subtree_check` | Evita comprobaciones adicionales de subdirectorios |
| `root_squash` | El `root` remoto se convierte en usuario sin privilegios (`nobody`) |
| `fsid=0` | Define la **raíz de exportación NFSv4** |

![Instalación de NFS](capturas/12a_nfs_instalar_servidor.png)

*Captura 12a — `capturas/12a_nfs_instalar_servidor.png`: instalación de `nfs-kernel-server`.*

![Servicio NFS activo](capturas/12b_nfs_servicio_activo.png)

*Captura 12b — `capturas/12b_nfs_servicio_activo.png`: activación del servicio NFS y comprobación de su estado.*

![Grupo y directorio compartido](capturas/12c_nfs_grupo_nutresa_gid2000.png)

*Captura 12c — `capturas/12c_nfs_grupo_nutresa_gid2000.png`: creación del grupo `nutresa` (GID 2000), del directorio `/srv/nfs/nutresa` y asignación de permisos `2770`.*

![Archivo /etc/exports](capturas/12d_nfs_directorio_y_exports.png)

*Captura 12d — `capturas/12d_nfs_directorio_y_exports.png`: archivo `/etc/exports` con la línea de exportación.*

Aplicar y verificar:

```bash
sudo exportfs -ra
sudo exportfs -v
sudo ss -lntp | grep 2049
sudo ufw allow from 192.168.1.0/24 to any port 2049 proto tcp
```

**Resultado esperado y obtenido:**

```text
/srv/nfs/nutresa
        192.168.1.0/24(sync,wdelay,hide,no_subtree_check,fsid=0,sec=sys,rw,secure,root_squash,no_all_squash)
LISTEN 0 64  0.0.0.0:2049  0.0.0.0:*
LISTEN 0 64     [::]:2049     [::]:*
```

![exportfs](capturas/13a_nfs_exportfs.png)

*Captura 13a — `capturas/13a_nfs_exportfs.png`: `exportfs -ra` y `exportfs -v`: subred autorizada y opciones aplicadas.*

![Puerto 2049](capturas/13b_nfs_puerto_2049.png)

*Captura 13b — `capturas/13b_nfs_puerto_2049.png`: puerto `2049` en escucha (`ss -lntp`).*

## 3.4 Cliente: instalar herramientas y montar el recurso

En `nutresa-cliente`:

```bash
sudo apt update
sudo apt install -y nfs-common
showmount -e 192.168.1.34
```

`showmount` debe listar: `/srv/nfs/nutresa 192.168.1.0/24`.

Se crea el **mismo grupo con el mismo GID** y se agrega al usuario:

```bash
sudo groupadd -g 2000 nutresa
sudo usermod -aG nutresa ubuntu
getent group nutresa          # nutresa:x:2000:ubuntu
newgrp nutresa
id                            # gid=2000(nutresa) groups=2000(nutresa),...
```

Se crea el punto de montaje y se monta:

```bash
sudo mkdir -p /mnt/nutresa
sudo mount -t nfs4 192.168.1.34:/ /mnt/nutresa
df -hT /mnt/nutresa
mount | grep nutresa
```


**Verificación.** `df -hT` muestra `192.168.1.34:/  nfs4  38G ... /mnt/nutresa` y `mount` indica `type nfs4 (rw,...,vers=4.2,...,proto=tcp,...,clientaddr=192.168.1.35)`: protocolo NFSv4.2 sobre TCP desde el cliente `192.168.1.35`.

## 3.5 Prueba de lectura y escritura cliente → servidor

Desde el cliente:

```bash
touch /mnt/nutresa/prueba_cliente.txt
echo "Prueba NFS desde el cliente Nutresa" > /mnt/nutresa/prueba_cliente.txt
cat /mnt/nutresa/prueba_cliente.txt
```

Para comprobarlo del lado del servidor:

```bash
ls -l /srv/nfs/nutresa/
```

Aquí apareció `Permission denied` (Problema 3.C): el usuario `ubuntu` del servidor aún no pertenecía al grupo `nutresa`. Se corrigió con:

```bash
sudo usermod -aG nutresa ubuntu
newgrp nutresa
groups
ls -l /srv/nfs/nutresa/
cat /srv/nfs/nutresa/prueba_cliente.txt
```

Resultado: `-rw-rw-r-- 1 ubuntu nutresa 36 ... prueba_cliente.txt` con contenido `Prueba NFS desde el cliente Nutresa`.

![Cliente: nfs-common](capturas/14a_nfs_cliente_instalar_herramientas.png)

*Captura 14a — `capturas/14a_nfs_cliente_instalar_herramientas.png`: cliente: instalación de `nfs-common` y consulta con `showmount -e 192.168.1.34`.*

![Cliente: grupo nutresa](capturas/14b_nfs_cliente_grupo_nutresa.png)

*Captura 14b — `capturas/14b_nfs_cliente_grupo_nutresa.png`: cliente: creación del grupo `nutresa` con GID 2000 y alta del usuario `ubuntu`.*

![Cliente: montaje NFSv4](capturas/14c_nfs_cliente_montaje.png)

*Captura 14c — `capturas/14c_nfs_cliente_montaje.png`: cliente: creación del punto de montaje y montaje NFSv4 (`mount`, `df -hT`).*

![Cliente: prueba de escritura](capturas/14d_nfs_cliente_prueba_escritura.png)

*Captura 14d — `capturas/14d_nfs_cliente_prueba_escritura.png`: cliente: escritura y lectura de `prueba_cliente.txt` en `/mnt/nutresa`.*

![Servidor: error de permisos](capturas/14e_nfs_servidor_error_permisos.png)

*Captura 14e — `capturas/14e_nfs_servidor_error_permisos.png`: servidor: `Permission denied` al listar el directorio (el usuario `ubuntu` no estaba en el grupo `nutresa`).*

![Servidor: permisos corregidos](capturas/14f_nfs_servidor_permisos_corregidos.png)

*Captura 14f — `capturas/14f_nfs_servidor_permisos_corregidos.png`: servidor: tras `usermod -aG nutresa ubuntu` y `newgrp nutresa` se lista el directorio y se lee el archivo.*

## 3.6 Montaje permanente en el cliente (`/etc/fstab`)

El montaje manual se pierde al reiniciar. Para hacerlo permanente:

```bash
sudo nano /etc/fstab
```

Se agrega al final:

```text
192.168.1.34:/ /mnt/nutresa nfs4 rw,_netdev,nofail,x-systemd.automount 0 0
```

| Opción | Función |
|---|---|
| `nfs4` | Tipo de sistema de archivos NFSv4 |
| `rw` | Lectura y escritura |
| `_netdev` | Indica que depende de la red (se monta después de levantar la red) |
| `nofail` | No impide el arranque si el servidor no está disponible |
| `x-systemd.automount` | Monta bajo demanda al acceder a la carpeta |

Aplicar y comprobar:

```bash
sudo systemctl daemon-reload
sudo mount -a
ls -la /mnt/nutresa
```

Se crea un archivo **desde el servidor** y se lee **desde el cliente**:

```bash
# En nutresa-server
echo "Documento creado desde el servidor Nutresa" | sudo tee /srv/nfs/nutresa/prueba_servidor.txt

# En nutresa-cliente
cat /mnt/nutresa/prueba_servidor.txt     # Documento creado desde el servidor Nutresa
```

![Línea en /etc/fstab](capturas/15a_nfs_fstab.png)

*Captura 15a — `capturas/15a_nfs_fstab.png`: línea de montaje permanente en `/etc/fstab` del cliente.*

![mount -a](capturas/15b_nfs_mount_a_verificacion.png)

*Captura 15b — `capturas/15b_nfs_mount_a_verificacion.png`: `daemon-reload`, `mount -a` y listado de `/mnt/nutresa`.*

![Servidor: archivo creado](capturas/15c_nfs_archivo_creado_en_servidor.png)

*Captura 15c — `capturas/15c_nfs_archivo_creado_en_servidor.png`: servidor: creación del archivo `prueba_servidor.txt`.*

![Cliente: lectura del archivo](capturas/15d_nfs_cliente_lee_archivo.png)

*Captura 15d — `capturas/15d_nfs_cliente_lee_archivo.png`: cliente: lectura de `prueba_servidor.txt` creado desde el servidor.*

## 3.7 Lista de verificación de la Sección 3

| Verificación | Comando | Resultado esperado | Captura |
|---|---|---|---|
| Directorio y permisos | `ls -ld /srv/nfs/nutresa` | `drwxrws--- root nutresa` | 12 |
| Exportación activa | `sudo exportfs -v` | `192.168.1.0/24(rw,...,root_squash,...,fsid=0)` | 13 |
| Puerto NFS | `sudo ss -lntp \| grep 2049` | `LISTEN 0.0.0.0:2049` | 13 |
| Cliente ve el export | `showmount -e 192.168.1.34` | `/srv/nfs/nutresa 192.168.1.0/24` | — |
| Montaje NFSv4 | `mount \| grep nutresa` | `type nfs4 (... vers=4.2 ...)` | 14 |
| Escritura cliente → servidor | `cat /srv/nfs/nutresa/prueba_cliente.txt` | contenido enviado por el cliente | 14 |
| Escritura servidor → cliente | `cat /mnt/nutresa/prueba_servidor.txt` | contenido creado en el servidor | 15 |
| Montaje permanente | `sudo mount -a` sin errores | `/mnt/nutresa` montado | 15 |

## 3.8 Solución de problemas de la Sección 3

| # | Problema | Causa | Solución |
|---|---|---|---|
| 3.A | `exportfs: can't open /etc/exports for reading` en el estado del servicio recién instalado. | El archivo `/etc/exports` aún no existía. | Es normal; se creó el archivo (3.3) y se ejecutó `sudo exportfs -ra`. |
| 3.B | En el primer cliente: `mount.nfs4: Operation not permitted for 192.168.1.34:/`. Después: `mount point does not exist`. | El cliente estaba en la red NAT (`10.0.2.15`, ruta por `10.0.2.2`), fuera de `192.168.1.0/24`, que es la única subred autorizada en `/etc/exports`; luego faltaba crear el punto de montaje. | Conectar el cliente a `192.168.1.0/24` (`192.168.1.35`), ejecutar `sudo mkdir -p /mnt/nutresa` y repetir el `mount`. |
| 3.C | En el servidor: `ls: cannot open directory '/srv/nfs/nutresa/': Permission denied` aunque el archivo sí había llegado. | El directorio es `2770 root:nutresa` y el usuario `ubuntu` del servidor no pertenecía al grupo `nutresa`. | `sudo usermod -aG nutresa ubuntu` y `newgrp nutresa`; verificar con `groups` (Captura 14). Alternativa sin cambiar de grupo: `sudo ls -l /srv/nfs/nutresa/`. |
| 3.D | Los permisos no coinciden entre equipos. | NFS compara UID/GID numéricos. | Mantener el mismo grupo `nutresa` con GID `2000` en servidor y cliente (y, en la Sección 4, el usuario NIS `nisprueba` con GID `2000`). |

---

# Sección 7. Traefik, dominio y SSL/TLS

**Objetivo.** Dejar el servidor `nutresa-server` accesible por un nombre de dominio real (`nutresa-admin.duckdns.org`) y con un certificado HTTPS válido de Let's Encrypt, usando el desafío **DNS-01** de ACME, que no requiere abrir puertos del router (la red es local, detrás del Wi-Fi).

**Resumen de lo realizado**

1. Apuntar el dominio de DuckDNS a la IP de servicio `192.168.1.34`.
2. Verificar la resolución DNS del dominio desde Windows y desde la VM.
3. Configurar Traefik con el proveedor `duckdns` y el desafío DNS-01 (primero con el servidor *staging* de Let's Encrypt).
4. Recrear el contenedor de Traefik con el token de DuckDNS.
5. Configurar el dominio en Dokploy.
6. Pasar del certificado de pruebas al certificado real de producción.
7. Probar el acceso HTTPS desde Windows y desde el navegador.

## 7.1 Dominio DNS con DuckDNS

### Apuntar el dominio a la IP privada

En el panel oficial de [DuckDNS](https://www.duckdns.org) se agrega un nuevo dominio, en este caso `nutresa-admin`, se escribe la IP `192.168.1.34` y se pulsa *update ip*. DuckDNS genera un token que, por razones de seguridad, no se comparte con nadie.

![Panel de DuckDNS](capturas/16a_duckdns_panel.png)

*Captura 16a — `capturas/16a_duckdns_panel.png`: panel de DuckDNS con el dominio `nutresa-admin` y la IP `192.168.1.34`.*

### Probar la resolución del dominio

Se prueba desde la terminal de Windows para confirmar que el dominio responde con la IP correcta:

```powershell
nslookup nutresa-admin.duckdns.org 8.8.8.8
nslookup nutresa-admin.duckdns.org
```

![nslookup con DNS público](capturas/16b_nslookup_dns_8888.png)

*Captura 16b — `capturas/16b_nslookup_dns_8888.png`: `nslookup` contra `8.8.8.8` devolviendo `192.168.1.34`.*

![nslookup con DNS predeterminado](capturas/16c_nslookup_dns_default.png)

*Captura 16c — `capturas/16c_nslookup_dns_default.png`: `nslookup` con el DNS predeterminado del sistema.*

Desde Ubuntu (`nutresa-server`) también se prueba:

```bash
getent hosts nutresa-admin.duckdns.org
```

![Resolución desde la VM](capturas/16d_getent_hosts_vm.png)

*Captura 16d — `capturas/16d_getent_hosts_vm.png`: resolución del dominio desde la VM.*

Con esto queda creado el dominio DNS.

## 7.2 Certificado SSL/TLS con Let's Encrypt (DNS-01)

Con el desafío **DNS-01**, Let's Encrypt no se conecta al servidor directamente: solo consulta un registro TXT que Traefik crea en DuckDNS con el token. Así no es necesario abrir puertos ni tocar el router.

### Revisar la configuración actual de Traefik

En el shell de `nutresa-server` se verifica cómo está Traefik y cuáles son los montajes del contenedor:

```bash
sudo docker exec dokploy-traefik traefik version
sudo docker inspect dokploy-traefik --format '{{json .Mounts}}'
sudo cat /etc/dokploy/traefik/traefik.yml
sudo ls -l /etc/dokploy/traefik/dynamic/
```

*(Captura pendiente.)*

Hallazgos: el resolver `letsencrypt` usaba el desafío **HTTP-01**, que necesita el puerto 80 abierto a internet y no funciona en una red local; además, el archivo `acme.json` tenía 0 bytes, es decir, nunca se había emitido un certificado.

### Copia de seguridad

Antes de proceder se guarda una copia de seguridad de la configuración por si algo falla:

```bash
sudo mkdir -p /root/backup-red
sudo cp -a /etc/dokploy/traefik/traefik.yml /root/backup-red/traefik.yml.bak
sudo ls -l /root/backup-red
```

![Copia de seguridad](capturas/17a_traefik_backup.png)

*Captura 17a — `capturas/17a_traefik_backup.png`: copia de seguridad de `traefik.yml` creada en `/root/backup-red`.*

### Guardar el token de forma segura

El token se guarda en un archivo que solo puede leer root, fuera del repositorio:

```bash
read -rsp "DUCKDNS_TOKEN: " T; echo
printf 'DUCKDNS_TOKEN=%s\n' "$T" | sudo tee /root/duckdns.env >/dev/null
sudo chmod 600 /root/duckdns.env
```

![Token guardado](capturas/17b_token_duckdns_env.png)

*Captura 17b — `capturas/17b_token_duckdns_env.png`: guardado del token de DuckDNS en `/root/duckdns.env`.*

El token no se guardó correctamente en el primer intento (el archivo quedó vacío); se resolvió escribiéndolo con `nano` (ver Problema 7.B):

```bash
sudo nano /root/duckdns.env
sudo chmod 600 /root/duckdns.env
sudo awk -F= '/^DUCKDNS_TOKEN=/{print "longitud en archivo:", length($2)}' /root/duckdns.env
```

![Token corregido](capturas/17c_token_correccion_nano.png)

*Captura 17c — `capturas/17c_token_correccion_nano.png`: corrección del token con `nano` y verificación de su longitud.*

### Editar `traefik.yml` (primero con staging)

Se cambia `httpChallenge` por `dnsChallenge` con el proveedor `duckdns`, se pone un correo real y, para probar sin gastar los límites de Let's Encrypt, se usa el servidor de pruebas (*staging*):

```bash
sudo nano /etc/dokploy/traefik/traefik.yml
```

El contenido queda así:

```yaml
global:
  sendAnonymousUsage: false
providers:
  swarm:
    exposedByDefault: false
    watch: true
  docker:
    exposedByDefault: false
    watch: true
    network: dokploy-network
  file:
    directory: /etc/dokploy/traefik/dynamic
    watch: true
entryPoints:
  web:
    address: :80
  websecure:
    address: :443
    http3:
      advertisedPort: 443
    http:
      tls:
        certResolver: letsencrypt
api:
  insecure: true
certificatesResolvers:
  letsencrypt:
    acme:
      email: <correo-del-equipo>
      storage: /etc/dokploy/traefik/dynamic/acme.json
      caServer: https://acme-staging-v02.api.letsencrypt.org/directory
      dnsChallenge:
        provider: duckdns
        resolvers:
          - "1.1.1.1:53"
          - "8.8.8.8:53"
```

![Edición de traefik.yml](capturas/17d_traefik_yml_dnschallenge.png)

*Captura 17d — `capturas/17d_traefik_yml_dnschallenge.png`: edición de `traefik.yml` con `dnsChallenge` y servidor *staging*.*

Se valida el archivo:

```bash
sudo python3 -c 'import yaml; yaml.safe_load(open("/etc/dokploy/traefik/traefik.yml")); print("YAML OK")'
```

![Validación YAML](capturas/17e_traefik_yml_yaml_ok.png)

*Captura 17e — `capturas/17e_traefik_yml_yaml_ok.png`: validación del YAML modificado.*

Traefik se reiniciaba en bucle y los sitios quedaban sin servicio por dos errores de escritura en el YAML; se corrigieron y el servicio volvió a la normalidad (ver Problemas 7.C y 7.D):

```bash
sudo sed -i 's/insercure/insecure/' /etc/dokploy/traefik/traefik.yml
sudo grep -n -B1 -A1 'insecure' /etc/dokploy/traefik/traefik.yml
sudo python3 -c 'import yaml; yaml.safe_load(open("/etc/dokploy/traefik/traefik.yml")); print("YAML OK")'
sudo docker restart dokploy-traefik
sleep 5
```

![Corrección del primer error](capturas/17f_traefik_fix_insecure.png)

*Captura 17f — `capturas/17f_traefik_fix_insecure.png`: corrección del primer error de escritura (`insercure` → `insecure`).*

```bash
sudo sed -i 's/exposeByDefault/exposedByDefault/' /etc/dokploy/traefik/traefik.yml
sudo grep -n 'exposedByDefault' /etc/dokploy/traefik/traefik.yml
sudo python3 -c 'import yaml; yaml.safe_load(open("/etc/dokploy/traefik/traefik.yml")); print("YAML OK")'
sudo docker restart dokploy-traefik
sudo docker logs --since 1m dokploy-traefik
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep traefik
```

![Corrección del segundo error](capturas/17g_traefik_fix_exposedbydefault.png)

*Captura 17g — `capturas/17g_traefik_fix_exposedbydefault.png`: corrección del segundo error de escritura (`exposeByDefault` → `exposedByDefault`).*

### Recrear Traefik con el token

La variable `DUCKDNS_TOKEN` debe existir dentro del contenedor, y un `docker restart` no añade variables de entorno. Por eso se recreó el contenedor con las mismas opciones que tenía, más `--env-file`. Solo se elimina el contenedor: los datos persisten en carpetas del servidor.

```bash
sudo docker rm -f dokploy-traefik
sudo docker run -d \
  --name dokploy-traefik \
  --restart always \
  --network dokploy-network \
  --env-file /root/duckdns.env \
  -v /etc/dokploy/traefik/traefik.yml:/etc/traefik/traefik.yml \
  -v /etc/dokploy/traefik/dynamic:/etc/dokploy/traefik/dynamic \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -p 80:80/tcp -p 443:443/tcp -p 443:443/udp \
  traefik:v3.6.25
```

![Contenedor recreado](capturas/17h_traefik_contenedor_recreado.png)

*Captura 17h — `capturas/17h_traefik_contenedor_recreado.png`: recreación del contenedor de Traefik con `--env-file`.*

Se comprueba que el token llegó al contenedor y se revisan los logs:

```bash
sudo docker exec dokploy-traefik printenv DUCKDNS_TOKEN | wc -c
sudo docker logs -f --since 1m dokploy-traefik 2>&1 | grep -iE 'acme|duckdns|certificate|error|unable'
```

![Token en el contenedor](capturas/17i_traefik_token_en_contenedor.png)

*Captura 17i — `capturas/17i_traefik_token_en_contenedor.png`: contenedor `dokploy-traefik` en ejecución con el token disponible.*

En los logs aparecía que no se podía obtener el certificado de ACME y que el certificado servido era `TRAEFIK DEFAULT CERT` (el de respaldo): Traefik reconocía el proveedor `duckdns`, pero por el token vacío no lo estaba leyendo bien (ver Problema 7.D).

![Logs de error del certificado](capturas/17j_traefik_logs_error_acme.png)

*Captura 17j — `capturas/17j_traefik_logs_error_acme.png`: logs de error del certificado antes de corregir el token.*

### Configurar el dominio en Dokploy

En el panel de Dokploy: proyecto → aplicación web `nutresa` → pestaña **Domains**, con estos valores:

| Campo | Valor |
|---|---|
| Host | `nutresa-admin.duckdns.org` |
| Path | `/` |
| Container Port | `80` |
| HTTPS | Activado |
| Certificate | Let's Encrypt |

![Dominio en Dokploy](capturas/17k_dokploy_dominio_https.png)

*Captura 17k — `capturas/17k_dokploy_dominio_https.png`: dominio configurado en Dokploy con HTTPS y certificado Let's Encrypt.*

Dokploy genera la ruta de Traefik en `/etc/dokploy/traefik/dynamic/my-first-project-nutresa-qmjfti.yml`, con un router `web` que redirige a HTTPS y un router `websecure` que usa `certResolver: letsencrypt`:

```bash
sudo cat /etc/dokploy/traefik/dynamic/my-first-project-nutresa-qmjfti.yml
```

*(Captura pendiente.)*

### Verificar el resultado de la prueba (staging)

```bash
sudo docker logs --since 2m dokploy-traefik 2>&1 | grep -iE 'acme|duckdns|certificate|error|unable'
echo | openssl s_client -connect 192.168.1.34:443 -servername nutresa-admin.duckdns.org 2>/dev/null | openssl x509 -noout -issuer -subject -dates
```

![Certificado de staging](capturas/17l_certificado_staging.png)

*Captura 17l — `capturas/17l_certificado_staging.png`: certificado de staging, issuer = (STAGING) Dastardly Durum YR1. La prueba DNS-01 funcionó correctamente.*

### Pasar al certificado real en producción

Se eliminó el `caServer` de `traefik.yml` y se vació `acme.json`, que solo contenía certificados de prueba. Traefik se detuvo solo unos segundos; `docker start` conserva la variable del token.

```bash
sudo nano /etc/dokploy/traefik/traefik.yml
sudo python3 -c 'import yaml; yaml.safe_load(open("/etc/dokploy/traefik/traefik.yml")); print("YAML OK")'
sudo docker stop dokploy-traefik
sudo truncate -s 0 /etc/dokploy/traefik/dynamic/acme.json
sudo chmod 600 /etc/dokploy/traefik/dynamic/acme.json
sudo docker start dokploy-traefik
sleep 60
echo | openssl s_client -connect 192.168.1.34:443 -servername nutresa-admin.duckdns.org 2>/dev/null | openssl x509 -noout -issuer -subject -dates
```

![Certificado de producción](capturas/17m_certificado_produccion.png)

*Captura 17m — `capturas/17m_certificado_produccion.png`: certificado de producción, issuer = Let's Encrypt, CN = YR2.*

Con esto se genera el certificado real de Let's Encrypt para `nutresa-admin.duckdns.org`, válido del 12 de noviembre de 2026 al 10 de febrero de 2027. Traefik lo renueva automáticamente unos 30 días antes de vencer.

### Probar el acceso desde Windows

Para comprobar que el certificado funciona se prueba el acceso a la página desde la terminal de Windows:

```powershell
Test-NetConnection nutresa-admin.duckdns.org -Port 443
curl.exe -I https://nutresa-admin.duckdns.org
curl.exe -I http://nutresa-admin.duckdns.org
```

![Prueba HTTPS desde Windows](capturas/17n_windows_prueba_https.png)

*Captura 17n — `capturas/17n_windows_prueba_https.png`: verificación de conexión con `200 OK` por HTTPS y `308` (redirección) por HTTP.*

Luego, en el navegador, se accede a la página:

![Acceso desde el navegador](capturas/17o_navegador_https.png)

*Captura 17o — `capturas/17o_navegador_https.png`: acceso desde el navegador para verificar el HTTPS.*

El navegador mostraba inicialmente el sitio como «no seguro», pero era por la caché del navegador (ver Problema 7.E): al abrirlo en una ventana de incógnito se confirmó que el certificado servía.

![Sitio seguro verificado](capturas/17p_navegador_sitio_seguro.png)

*Captura 17p — `capturas/17p_navegador_sitio_seguro.png`: verificación de sitio seguro en el navegador.*

## 7.3 Lista de verificación de la Sección 7

| Verificación | Comando | Resultado esperado | Captura |
|---|---|---|---|
| Dominio apunta a la IP de servicio | `nslookup nutresa-admin.duckdns.org` | `192.168.1.34` | 16 |
| Resolución desde la VM | `getent hosts nutresa-admin.duckdns.org` | `192.168.1.34` | 16 |
| Copia de seguridad de Traefik | `sudo ls -l /root/backup-red` | `traefik.yml.bak` presente | 17 |
| Token protegido | `sudo ls -l /root/duckdns.env` | permisos `-rw------- (600)` | 17 |
| YAML válido | `python3 -c 'yaml.safe_load(...)'` | `YAML OK` | 17 |
| Token dentro del contenedor | `docker exec dokploy-traefik printenv DUCKDNS_TOKEN` | imprime el token | 17 |
| Certificado de producción | `openssl s_client ... \| openssl x509 -noout -issuer` | issuer = Let's Encrypt (producción) | 17 |
| HTTPS desde Windows | `curl.exe -I https://nutresa-admin.duckdns.org` | `HTTP/... 200 OK` | 17 |

## 7.4 Solución de problemas de la Sección 7

| # | Problema | Causa | Solución |
|---|---|---|---|
| 7.A | El resolver `letsencrypt` no podía emitir certificados: usaba el desafío HTTP-01. | HTTP-01 necesita el puerto 80 abierto a internet y no funciona en una red local. | Cambiar a `dnsChallenge` con el proveedor `duckdns` en `traefik.yml` (Sección 7.2). |
| 7.B | El token de DuckDNS no se guardó: `/root/duckdns.env` quedó vacío. | El guardado interactivo con `read`/`printf` falló. | Escribir el token con `sudo nano /root/duckdns.env`, `chmod 600` y verificar la longitud con `awk` (Captura 17c). |
| 7.C | Traefik se reiniciaba en bucle y los sitios quedaban sin servicio. | Dos errores de escritura en `traefik.yml`: `insercure` en lugar de `insecure` y `exposeByDefault` en lugar de `exposedByDefault`. | Corregir ambos con `sed`, validar el YAML y reiniciar el contenedor (Capturas 17f y 17g). |
| 7.D | Los logs mostraban fallo de ACME y el certificado servido era `TRAEFIK DEFAULT CERT` (el de respaldo). | Traefik reconocía el proveedor `duckdns`, pero leía el token vacío del Problema 7.B. | Corregir el token (7.B) y recrear el contenedor con `--env-file` (Captura 17j). |
| 7.E | El navegador mostraba el sitio como «no seguro» con el certificado real ya emitido. | Caché del navegador con el certificado anterior. | Verificar en una ventana de incógnito; el candado apareció correctamente (Captura 17p). |

---

*Fin de las secciones 1 a 3. Las secciones 4 a 9 son responsabilidad de los Integrantes 2 y 3.*
