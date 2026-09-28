Requerimientos para la actualización de la aplicación

Actualmente, la aplicación cuenta únicamente con usuarios registrados de forma predeterminada en la base de datos y no dispone de un módulo para registrar nuevas empresas o usuarios. Asimismo, el panel actual permite visualizar las empresas de manera individual, pero se requiere implementar una gestión centralizada que permita administrar múltiples empresas pertenecientes a un mismo contador.

A continuación, se detallan los cambios y funcionalidades requeridas.

3. Gestión de correos electrónicos

El sistema deberá permitir registrar información de los periodos procesados por cada empresa y enviar a dichos correos la información por correo. por ejemplo en local el único correo que se le podrá enviar correos será espinozavaleracinve@gmail.com

Se deberá poder colocar lo siguiente:

- Correo registrado.
- Empresas asociadas.
- Períodos procesados.
- Fecha del proceso.
- Estado del envío.

---

4. Descarga de reportes SIRE

El sistema deberá permitir realizar la descarga de los reportes correspondientes a las empresas registradas.

La descarga podrá ejecutarse para:

- Una empresa específica.
- Un período específico.
- Varios períodos.
- Todas las empresas registradas.

El proceso deberá ejecutarse mediante una cola de trabajos (queue) para evitar que el usuario tenga que mantener abierta la página durante todo el proceso.

Por ejemplo:

1. Empresa 1 → descarga de reportes SIRE.
2. Empresa 2 → descarga de reportes SIRE.
3. Empresa 3 → descarga de reportes SIRE.
4. Continuar hasta procesar todas las empresas pendientes.

El sistema deberá mantener el estado de cada tarea y permitir identificar si fue completada, está pendiente, se encuentra en proceso o presentó un error.

---

5. Descarga de comprobantes

Una vez procesados los reportes SIRE, el sistema deberá realizar automáticamente la descarga de los comprobantes correspondientes.

Esta descarga también deberá ejecutarse mediante una cola de trabajos y en segundo plano.

El usuario no deberá permanecer conectado a la aplicación para que el proceso continúe. El contador podrá cerrar la página o dejar de utilizar la aplicación y las tareas deberán continuar ejecutándose en el servidor.

La secuencia general será:

Descarga de reporte SIRE → procesamiento → descarga de comprobantes → procesamiento/clasificación mediante IA → generación de archivos finales.

---

6. Descarga masiva de comprobantes

El dashboard deberá contar con una opción que permita seleccionar:

- Una empresa.
- Un período.
- Varios períodos.
- Varias empresas.
- Todos los períodos disponibles de todas las empresas.

A partir de esta selección, el sistema deberá generar automáticamente las tareas correspondientes y agregarlas a la cola de procesamiento.

---

7. Automatización de códigos mediante IA

La aplicación deberá automatizar el proceso de obtención/clasificación de los códigos mediante inteligencia artificial.

El sistema deberá:

1. Identificar los comprobantes que ya cuentan con un código válido.
2. No volver a procesar innecesariamente los comprobantes que ya fueron clasificados.
3. Identificar los comprobantes que se encuentren como "Sin clasificar" o que no tengan código.
4. Enviar automáticamente estos comprobantes a la IA para obtener su código correspondiente.
5. Registrar el resultado obtenido.
6. Reintentar automáticamente aquellos comprobantes cuyo procesamiento haya fallado.
7. Continuar realizando reintentos hasta completar el procesamiento, considerando también un mecanismo para identificar y controlar errores persistentes.

De esta manera, el sistema deberá intentar conseguir los códigos de todos los comprobantes posibles sin requerir intervención manual del usuario.

---

8. Procesamiento en segundo plano

Todos los procesos pesados deberán ejecutarse en segundo plano mediante una cola de tareas.

Esto incluye:

- Descarga de reportes SIRE.
- Descarga de comprobantes.
- Procesamiento de comprobantes.
- Solicitudes a la IA.
- Reintentos de procesos fallidos.
- Generación de archivos Excel.
- Organización de carpetas.
- Generación de archivos ZIP.
- Envío de correos electrónicos.

El objetivo es que el contador pueda iniciar el proceso y posteriormente cerrar la aplicación sin interrumpir las tareas.

---

9. Sistema de reintentos

Los procesos que fallen temporalmente deberán contar con un mecanismo automático de reintentos.

Por ejemplo, si durante la descarga de un comprobante o durante una solicitud a la IA se produce un error temporal, el sistema deberá volver a intentar la operación automáticamente.

Cada tarea deberá mantener información sobre:

- Número de intentos.
- Último intento realizado.
- Estado actual.
- Motivo del error, cuando corresponda.
- Fecha y hora del último intento.

Esto permitirá evitar que una falla puntual detenga todo el procesamiento de las empresas restantes.

---

10. Generación y organización de archivos

Una vez finalizado el procesamiento, los archivos deberán organizarse automáticamente siguiendo la estructura actualmente establecida por la aplicación.

Para cada empresa se deberá generar una carpeta utilizando el siguiente formato:

RUC_FECHA_PERÍODO_FECHA_ÚLTIMA_ACTUALIZACIÓN

Por ejemplo:

20123456789_2026-09_2026-09-27

Donde:

- "20123456789" corresponde al RUC.
- "2026-09" corresponde al período procesado.
- "2026-09-27" corresponde a la fecha de la última actualización/descarga realizada desde SIRE.

Dentro de cada carpeta se deberá mantener la estructura actual de archivos, incluyendo:

- Reporte de ventas.
- Reporte de compras.
- Archivos Excel correspondientes.
- Carpetas de comprobantes.
- Facturas.
- Boletas.
- Otros tipos de comprobantes que correspondan.

---

11. Generación de ZIP

Una vez finalizado el procesamiento de todas las empresas y períodos seleccionados, el sistema deberá generar automáticamente un archivo ZIP.

El ZIP deberá contener las carpetas correspondientes a cada empresa y período procesado.

Ejemplo de estructura:

DESCARGA_2026-09-27.zip
│
├── 20123456789_2026-08_2026-09-27/
│   ├── Ventas/
│   │   └── Reporte_Ventas.xlsx
│   ├── Compras/
│   │   └── Reporte_Compras.xlsx
│   └── Comprobantes/
│       ├── Facturas/
│       ├── Boletas/
│       └── Otros/
│
├── 20987654321_2026-08_2026-09-27/
│   ├── Ventas/
│   ├── Compras/
│   └── Comprobantes/
│
└── ...

La estructura interna deberá conservar la organización que actualmente utiliza la aplicación.

---

12. Notificación por correo electrónico

Cuando finalicen todos los procesos correspondientes a la solicitud, el sistema deberá enviar automáticamente un correo electrónico al usuario registrado.

El correo deberá informar que el proceso ha finalizado e indicar que se han completado:

- Descarga de reportes SIRE.
- Descarga de comprobantes.
- Procesamiento/clasificación mediante IA.
- Generación de los archivos finales.

El correo deberá incluir el archivo ZIP generado o, dependiendo de las limitaciones del servicio de correo, un enlace seguro para descargarlo.

El envío deberá realizarse únicamente cuando hayan terminado los procesos correspondientes a todas las empresas y períodos incluidos en la solicitud.

---

13. Flujo general del sistema

El flujo esperado sería el siguiente:

1. Registro de empresas

↓

2. El contador selecciona empresas y períodos

↓

3. Se generan las tareas en la cola

↓

4. Descarga de reportes SIRE

↓

5. Descarga de comprobantes

↓

6. Identificación de comprobantes sin código

↓

7. Procesamiento mediante IA

↓

8. Reintento automático de tareas fallidas

↓

9. Generación y organización de archivos

↓

10. Generación del ZIP general

↓

11. Envío de correo al contador

↓

12. El contador recibe el resultado final

---

14. Objetivo principal

El objetivo de estos cambios es convertir la aplicación actual, que funciona principalmente para consultar y procesar empresas de manera individual, en una plataforma capaz de administrar y procesar múltiples empresas de forma centralizada y automatizada.

El contador deberá poder registrar sus empresas, seleccionar los períodos que desea procesar, iniciar el proceso y dejar que el sistema realice automáticamente todas las tareas en segundo plano.

De esta manera, no será necesario que el contador permanezca conectado a la aplicación durante las descargas ni durante el procesamiento de los comprobantes. Una vez que todos los procesos hayan terminado, recibirá una notificación por correo con el archivo ZIP correspondiente a todas las empresas y períodos procesados.