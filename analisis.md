# Análisis y Diseño de Infraestructura TI - Grupo Nutresa

## **1. Contexto empresarial**

Grupo Nutresa S.A. es una empresa colombiana líder en alimentos procesados, con sede en Medellín y presencia directa en 18 países. Opera ocho unidades de negocio: Cárnicos, Galletas, Chocolates, Cafés, Tresmontes Lucchetti, Alimentos al Consumidor, Helados y Pastas.

La compañía desarrolla procesos de producción, comercialización y distribución de alimentos, además de servicios comerciales, logísticos y administrativos transversales. Su estrategia de transformación digital busca modernizar el núcleo tecnológico, mejorar la cadena de suministro, integrar sistemas mediante APIs y fortalecer la seguridad de sus activos digitales.

Para este proyecto se simula la infraestructura TI de una sede corporativa de Nutresa. El objetivo es centralizar, sobre un servidor Linux local, los servicios web, de archivos, de impresión, de sincronización horaria, de autenticación de usuarios y de acceso compartido, utilizando Dokploy como plataforma PaaS.

## **2. Necesidades identificadas**

| Necesidad | Problema o requerimiento | Servicio propuesto |
|---|---|---|
| Gestión de aplicaciones | Centralizar el despliegue, actualización y administración de aplicaciones web | Dokploy con Traefik como reverse proxy |
| Presencia digital institucional | Publicar información corporativa, marcas, productos y contacto de forma segura | Web Server (Nginx) desplegado con Dokploy |
| Lógica de negocio e integración | Procesar formularios y consultar noticias y productos desde la web | Backend API desplegada con Dokploy |
| Administración de la plataforma | Gestionar aplicaciones, dominios y certificados desde una interfaz web | Panel Admin (Dokploy) |
| Persistencia de datos | Almacenar información de la aplicación institucional | PostgreSQL mediante Dokploy |
| Nombre de dominio y cifrado | Acceder a los servicios por nombre y proteger el tráfico | Dominio/DNS dinámico y SSL/TLS (Let's Encrypt o autofirmado) |
| Sincronización de tiempo | Mantener la hora uniforme en servidores, estaciones y registros de auditoría | NTP |
| Archivos para Linux | Compartir documentación técnica, reportes y archivos operativos entre equipos Linux | NFS |
| Autenticación centralizada | Administrar usuarios y credenciales desde un punto central | NIS |
| Impresión compartida | Permitir que varias áreas usen impresoras de red desde una cola central | CUPS |
| Archivos para Windows/Mac | Compartir carpetas corporativas con equipos Windows y macOS | Samba |

## **3. Justificación de los servicios propuestos**

### **3.1 Dokploy y Traefik**
Dokploy permite administrar aplicaciones contenerizadas desde una interfaz centralizada. Se instaló en `nutresa-server` (Dokploy v0.31.0 sobre Docker 28.5 en modo Swarm, con Traefik v3.6.25) declarando la IP de servicio `192.168.1.34` durante la instalación. Dokploy se usa como plataforma PaaS para desplegar el sitio institucional, la API y la base de datos. Traefik actúa como reverse proxy: recibe el tráfico en los puertos 80 y 443, lo enruta hacia los contenedores correspondientes y gestiona los certificados SSL/TLS.

**Justificación:** reduce la administración manual de servicios web, facilita despliegues reproducibles desde un repositorio Git y centraliza el acceso seguro por HTTPS.

### **3.2 Web Server (Nginx)**
Se implementó un sitio institucional de Grupo Nutresa como página estática servida por Nginx dentro de un contenedor (`nginx:alpine`). Se despliega en Dokploy desde el repositorio Git del proyecto. El sitio presenta la compañía, sus unidades de negocio y un formulario de contacto, y se publica por HTTPS en `nutresa-admin.duckdns.org`.

**Justificación:** Nutresa requiere una presencia web segura para clientes, proveedores, inversionistas y empleados. Al ejecutarse como contenedor en Dokploy, no se instala un servidor web en el host y se evitan conflictos con los puertos 80 y 443 de Traefik.

### **3.3 Backend API**
Se desarrolló una API REST con FastAPI que se despliega como aplicación en Dokploy a partir del mismo repositorio. Expone tres rutas: `/` (información del servicio), `/health` (estado) y `/productos` (consulta y registro de productos, con GET y POST). Se conecta a PostgreSQL mediante la variable de entorno `DATABASE_URL`, a través de la red interna de Docker.


**Justificación:** separa la presentación (sitio web) de la lógica y el acceso a datos, evita exponer la base de datos y permite actualizar cada componente de forma independiente.

### **3.4 Panel Admin (Dokploy)**
El panel web de Dokploy es el punto de administración de aplicaciones, dominios, certificados y bases de datos. Se accede desde `http://192.168.1.34:3000`, y el acceso está permitido únicamente a las IPs de los administradores (`192.168.1.31` y `192.168.1.15`).

**Justificación:** concentra la gestión de la plataforma en una sola interfaz y limita su acceso a los administradores de TI.

### **3.5 Dominio/DNS y SSL/TLS**
Se registró el dominio gratuito `nutresa-admin.duckdns.org` en DuckDNS, apuntando a la IP de servicio `192.168.1.34`.  Traefik se configuró para validar el certificado mediante el **desafío DNS-01**, usando el token de DuckDNS. Se verifica desde el host Windows que el sitio responde por HTTPS con código 200 y que el tráfico HTTP se redirige a HTTPS (código 308).


**Justificación:** permite cifrar todo el tráfico web, acceder a los servicios por nombre y no por IP y puerto, y obtener un certificado válido sin exponer el servidor a internet.

### **3.6 NTP**
El servicio NTP se implementó con **Chrony**, el servicio de sincronización estándar y mantenido en Ubuntu 24.04, que cumple la misma función que el paquete `ntp`  (cliente y servidor NTP) y se verifica con `chronyc`. El servidor toma la hora de las fuentes de Ubuntu (`ntp.ubuntu.com` y el pool de Ubuntu), queda en estrato 3 y ofrece la hora a la red `192.168.1.0/24` mediante la directiva `allow 192.168.1.0/24`. El cliente `nutresa-cliente` se configuró con `server 192.168.1.34 iburst` y quedó sincronizado con el servidor local (estrato 4).

**Justificación:** la sincronización horaria es necesaria para registros de acceso, bitácoras, respaldos, certificados SSL, autenticación y trazabilidad operativa. Al instalar Chrony, Ubuntu retira `systemd-timesyncd`, por lo que no hay dos servicios compitiendo por el reloj.

### **3.7 NFS**
NFS comparte el directorio corporativo `/srv/nfs/nutresa` con los clientes Linux de la red. Se usa **NFSv4** con `fsid=0`, de modo que todo el tráfico viaja por el puerto 2049/TCP. La exportación está limitada a `192.168.1.0/24`, con `rw`, `sync`, `no_subtree_check` y `root_squash`. El directorio pertenece a `root:nutresa` con permisos `2770` (bit setgid), y el grupo `nutresa` tiene GID 2000 igual en servidor y cliente. El cliente monta el recurso en `/mnt/nutresa` (NFSv4.2 sobre TCP) y el montaje es permanente mediante `/etc/fstab`.

**Justificación:** permite centralizar archivos técnicos, reportes, documentos de calidad y material operativo. Como NFS identifica a los usuarios por UID/GID numéricos, mantener el mismo GID en todos los equipos asegura permisos consistentes; `root_squash` evita que el `root` remoto tenga privilegios en el servidor.

### **3.8 NIS**
NIS centraliza las cuentas de usuario de los clientes Linux bajo el dominio `nutresa.local`. El servidor se inicializó con `ypinit -m`; los puertos de `ypserv` y `yppasswdd` se fijaron en 1011 y 1012 (en `/etc/default/nis`) para poder filtrarlos, y el acceso se limitó a `192.168.1.0/24` con `/etc/ypserv.securenets`. Se creó el usuario de prueba `nisprueba` (UID 2101, GID 2000) y el cliente se vinculó al servidor con `domain nutresa.local server 192.168.1.34` en `/etc/yp.conf`. La verificación en el cliente fue exitosa: `ypwhich` devuelve `192.168.1.34` y `getent passwd nisprueba` entrega la cuenta centralizada.

**Justificación:** evita crear manualmente el mismo usuario en cada equipo Linux. Además, los UID/GID centralizados hacen consistentes los permisos de NFS entre equipos (el usuario `nisprueba` pertenece al grupo `nutresa`, GID 2000).

**Consideración de seguridad:** NIS es un protocolo antiguo que no cifra la información de las cuentas, por lo que su uso se limita a la red local, restringido por UFW y por la opción `securenets`. En un entorno productivo real se recomendaría migrar a LDAP o FreeIPA; aquí se usa por ser requisito del proyecto.

### **3.9 CUPS**
CUPS administra las colas de impresión desde el servidor. Se habilitó la administración desde la red local (escucha en el puerto 631) y, al no contar con una impresora física, se creó la impresora virtual **`Nutresa-PDF`** con `cups-pdf`. Se probó el servicio enviando un trabajo con `lp -d Nutresa-PDF`, que generó el archivo PDF correspondiente, y se accedió al panel web desde el host Windows en `https://192.168.1.34:631`.

**Justificación:** permite que usuarios de diferentes áreas envíen trabajos de impresión a través de un servidor centralizado, por ejemplo etiquetas internas, órdenes de producción, reportes de calidad y guías de despacho.

### **3.10 Samba**
Samba comparte la carpeta corporativa con clientes Windows y macOS. El recurso se llama **`[Corporativo]`** y apunta a `/srv/samba/corporativo`. El acceso requiere autenticación: solo pueden entrar los miembros del grupo `sambausers` (`valid users = @sambausers`), con `force group = sambausers` y máscaras `0660` para archivos y `02770` para directorios. No se habilita el acceso de invitados. El usuario `sambanutresa` se creó sin shell de inicio de sesión (`/usr/sbin/nologin`) y con contraseña propia de Samba (`smbpasswd`). Se probó desde el host Windows: se autenticó, accedió a la carpeta y creó un archivo que luego se verificó en el servidor. El servicio usa el puerto 445/TCP.

**Justificación:** permite interoperabilidad con los sistemas operativos de escritorio de las oficinas sin exponer el sistema de archivos completo del servidor.

### **3.11 PostgreSQL**
PostgreSQL se desplegó desde Dokploy como servicio independiente (imagen `postgres:18`) con la base de datos `nutresa-db` y el usuario `nutresa-admin`. Se comprobó su funcionamiento con `psql` dentro del contenedor (consulta de versión, creación de una tabla de prueba e inserción de un registro). El puerto 5432 no se publica: solo es accesible desde la red interna de Docker, donde la Backend API se conecta mediante `DATABASE_URL`. **

**Justificación:** es un gestor relacional que permite almacenar y consultar los datos de la aplicación (en la implementación, el catálogo de productos). Al no publicar el puerto, se reduce la superficie de ataque.

## **4. Diagrama de arquitectura**

El diagrama completo se encuentra en el archivo `diagrama.mmd`.

**Descripción:** el tráfico web de la red local llega a Dokploy/Traefik, que lo distribuye al Web Server, a la Backend API y al Panel Admin. DuckDNS resuelve el dominio hacia la IP del servidor y el certificado se obtiene mediante el desafío DNS-01. La base de datos PostgreSQL se despliega dentro de Dokploy y solo es accesible por la Backend API a través de la red interna de Docker. Por otro lado, `nutresa-server` ofrece directamente NTP, NFS, NIS, CUPS y Samba: NTP, NFS y NIS atienden al cliente Linux, y Samba y CUPS al cliente Windows.

## **5. Tabla de requisitos técnicos**

Servidor: Ubuntu Server 24.04.5 LTS (`nutresa-server`), IP de servicio `192.168.1.34/24` (interfaz `eth1`, fijada como dirección adicional en Netplan con DHCP activo). Cliente Linux: `192.168.1.35`. Host Windows (cliente y administrador): `192.168.1.31`. Dominio: `nutresa-admin.duckdns.org`. Dominio NIS: `nutresa.local`.

| Servicio | IP del servidor | Puerto | Protocolo | Tipo de servicio | Cliente o consumidor | Alcance |
|---|---|---|---|---|---|---|
| Dokploy / Traefik | 192.168.1.34 | 80, 443 | HTTP, HTTPS/TCP | Proxy inverso y SSL | Navegadores y aplicaciones | Red local |
| Panel Admin (Dokploy) | 192.168.1.34 | 3000 | HTTP/TCP | PaaS / Panel web | Administradores TI | Solo 192.168.1.31 y 192.168.1.15 |
| Web Server (Nginx) | 192.168.1.34 | 443 (vía Traefik) | HTTPS/TCP | Servidor web | Usuarios de la red local | Red local |
| Backend API | 192.168.1.34 | 443 (vía Traefik) **[CONFIRMAR ruta o subdominio]** | HTTPS/TCP | API REST | Aplicación web | Red local |
| PostgreSQL | Red interna Docker | 5432 (no publicado) | TCP | Base de datos | Backend API | Solo red interna Docker |
| DNS / dominio | DuckDNS (externo) | 53 (salida) | UDP/TCP | Resolución de nombres | Todos los equipos | Externo |
| Let's Encrypt (validación DNS-01) | — | 443 (salida de Traefik hacia DuckDNS y Let's Encrypt) | HTTPS/TCP | Emisión de certificados | Traefik | Sin tráfico entrante |
| NTP | 192.168.1.34 | 123 | UDP | Sincronización horaria | Clientes Linux | Subred 192.168.1.0/24 |
| NFS (v4) | 192.168.1.34 | 2049 | TCP | Compartición de archivos | Clientes Linux | Subred 192.168.1.0/24 |
| NIS (portmapper) | 192.168.1.34 | 111 | TCP/UDP | Autenticación centralizada | Clientes Linux | Subred 192.168.1.0/24 |
| NIS (ypserv, puerto fijado) | 192.168.1.34 | 1011 | TCP/UDP | Autenticación centralizada | Clientes Linux | Subred 192.168.1.0/24 |
| NIS (yppasswdd, puerto fijado) | 192.168.1.34 | 1012 | TCP/UDP | Cambio de contraseña | Clientes Linux | Subred 192.168.1.0/24 |
| CUPS (IPP / panel web) | 192.168.1.34 | 631 | HTTP/HTTPS/TCP | Servidor de impresión | Clientes Linux y Windows | Subred 192.168.1.0/24 |
| Samba (SMB) | 192.168.1.34 | 445 | TCP | Compartición de archivos | Clientes Windows/Mac | Subred 192.168.1.0/24 |
| SSH administrativo | 192.168.1.34 | 22 | TCP | Administración remota | Administradores TI | Red local |

**Notas:**
- Los puertos 1011 y 1012 se fijan en `/etc/default/nis` (`YPSERVARGS="-p 1011"` y `YPPASSWDDARGS="--port 1012"`) para poder filtrarlos con el firewall, ya que por defecto NIS usa puertos dinámicos.
- Samba usa solo el puerto 445 (SMB directo), suficiente para clientes Windows 11 y macOS; no se habilitaron los puertos NetBIOS (137, 138, 139).
- Los puertos publicados por Docker (80, 443 y 3000) no son filtrados por las reglas de UFW, porque Docker los gestiona directamente con iptables; la restricción del puerto 3000 se complementa con el control de acceso de la propia plataforma.


## **6. Decisiones de diseño**

- Se usó **Ubuntu Server 24.04.5 LTS** por ser una distribución estable, ampliamente documentada y compatible con los servicios requeridos.
- La virtualización se realizó con **Multipass sobre Hyper-V** en un host Windows 11, en lugar de VirtualBox o VMware, por ser el hipervisor disponible en el equipo anfitrión. El servidor cumple los mínimos del proyecto (2 vCPU, 4 GB de RAM, 40 GB de disco).
- La red usa un **switch virtual externo** (`Nutresa-External`) ligado al adaptador Wi-Fi, de modo que la VM queda en la red local `192.168.1.0/24` (modo *bridged*). La VM tiene dos interfaces: `eth0` (red interna NAT) y `eth1` (red local).
- La IP de servicio `192.168.1.34` se configuró como **dirección adicional en `eth1`**, manteniendo el DHCP activo, para que los servicios no dejen de responder si el DHCP asigna otra dirección.
- Los servicios web, API y base de datos se despliegan mediante **Dokploy**, mientras que NTP, NFS, NIS, CUPS y Samba se instalaron directamente en el servidor Linux.
- Se usó **Traefik** como punto único de entrada HTTP/HTTPS; no se instaló otro servidor web en el host para evitar conflictos de puertos.
- Se usó **Chrony** en lugar del paquete `ntp`, por ser el servicio mantenido en Ubuntu 24.04 y cumplir la misma función.
- Como el servidor está en una IP privada, el certificado SSL se obtiene con el **desafío DNS-01** mediante DuckDNS, en lugar de HTTP-01.
- Se usó **NFSv4** limitado a la subred local (`192.168.1.0/24`) con `root_squash` activo, y permisos por grupo (`nutresa`, GID 2000), para reducir el riesgo de acceso no autorizado.
- **NIS** se restringió a la subred local mediante `securenets`, dado que no cifra la información de las cuentas.
- **Samba** requiere autenticación de usuarios del grupo `sambausers`; no se habilitó el acceso de invitados.
- **CUPS** se publica en la red local y se probó con una impresora virtual (`cups-pdf`) al no haber impresora física.
- **PostgreSQL** no se publica fuera de la red interna de Docker.
- El acceso al panel de Dokploy (puerto 3000) se limita a las IPs de los administradores.

## **7. Beneficios esperados**

- Centralización de servicios en un solo servidor local, accesible en `192.168.1.34`.
- Administración más simple de aplicaciones mediante Dokploy.
- Acceso seguro al sitio institucional mediante HTTPS.
- Sincronización horaria confiable en toda la red.
- Archivos corporativos disponibles para Linux, Windows y macOS.
- Autenticación centralizada de usuarios Linux mediante NIS.
- Impresión compartida y controlada mediante CUPS.
- Base de datos PostgreSQL integrada a la plataforma y accesible solo para la API.
## **8. Análisis costo-beneficio**

| Componente | Costo de licencia | Observación |
|---|---|---|
| Ubuntu Server | $0 | Software libre |
| Dokploy, Traefik, Docker | $0 | Software libre |
| Nginx, PostgreSQL | $0 | Software libre |
| NTP, NFS, NIS, CUPS, Samba | $0 | Incluidos en repositorios de Ubuntu |
| Certificados SSL (Let's Encrypt) | $0 | Renovación automática |
| Dominio | $0 (DNS dinámico gratuito) | Un dominio propio tendría un costo anual |
| Hardware | Servidor local existente | Costo de energía y mantenimiento |
| Multipass y Hyper-V | $0 | Multipass es software libre; Hyper-V viene incluido en el Windows del equipo anfitrión |

**Costos:** al usar solo software libre, el costo se concentra en el tiempo de implementación y administración del personal de TI y en el hardware existente. Un equivalente con licencias (Windows Server, servidor de impresión y servicio de autenticación comerciales) implicaría costos recurrentes por licencia y acceso de clientes.

**Beneficios:** menor costo de licenciamiento, administración centralizada, despliegues reproducibles y una base de infraestructura que puede crecer.

**Riesgos y limitaciones:** un único servidor es un punto de falla (se mitiga con respaldos de configuración y snapshots de la VM). NIS tiene limitaciones de seguridad (se mitiga restringiéndolo a la red local). El dominio gratuito de DuckDNS depende de un tercero y apunta a una IP privada, por lo que el sitio solo es accesible desde la red local. Por último, la dirección de la VM puede cambiar por DHCP; se mitigó fijando la IP de servicio como dirección adicional.