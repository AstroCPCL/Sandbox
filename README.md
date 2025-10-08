# Sandbox

Herramienta de línea de comandos para analizar tu bandeja de entrada IMAP y generar un reporte en Excel con la información clave de cada correo.

## Características

- Conexión a servidores IMAP (con o sin SSL).
- Detección automática de prioridad basándose en cabeceras y palabras clave.
- Estimación de fechas de vencimiento en base a cabeceras comunes o expresiones en el texto.
- Identificación de correos con gestiones pendientes (tareas).
- Exportación de los resultados a un Excel ordenado por estado (leído/no leído) y fecha de recepción.

## Requisitos

Instala las dependencias con:

```bash
pip install -r requirements.txt
```

## Configuración

Puedes definir las siguientes variables de entorno para evitar pasarlas como argumentos:

- `EMAIL_HOST`: Servidor IMAP (por ejemplo, `imap.gmail.com`).
- `EMAIL_USER`: Usuario de la cuenta de correo.
- `EMAIL_PASSWORD`: Contraseña de la cuenta o token de aplicación.
- `EMAIL_MAILBOX`: Carpeta a revisar (por defecto `INBOX`).
- `LOG_LEVEL`: Nivel de logging (por defecto `INFO`).

## Uso

Ejecuta el comando principal:

```bash
python main.py --host imap.servidor.com --username usuario@dominio.com --output reporte.xlsx
```

Si omites la contraseña, se solicitará de forma interactiva. Otros argumentos útiles:

- `--limit`: Número máximo de correos a procesar.
- `--mailbox`: Cambia el buzón/carpeta a revisar.
- `--no-ssl`: Desactiva SSL (no recomendado a menos que el servidor lo requiera).
- `--port`: Especifica un puerto IMAP personalizado.
- `--log-level`: Ajusta el nivel de detalle de los logs.

El Excel generado incluirá las columnas:

- `UID`: Identificador único del correo en el buzón.
- `Asunto`
- `Remitente`
- `Fecha de recepción`
- `Fecha de vencimiento`
- `Prioridad`
- `Estado`: Leído o No leído.
- `Pendiente`: Indica si se identificó una gestión/tarea pendiente.

## Notas

- Para bandejas muy grandes puedes utilizar `--limit` para reducir el número de correos procesados.
- El cálculo de fechas de vencimiento y pendientes se basa en heurísticas y puede requerir ajuste según tu contexto.
