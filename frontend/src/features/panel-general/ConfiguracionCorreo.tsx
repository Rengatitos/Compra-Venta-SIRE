import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import { useState } from 'react';

import {
  enviarCorreoPrueba,
  guardarConfiguracionCorreo,
  obtenerConfiguracionCorreo,
  previsualizarCorreo,
} from '@/api/correos';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { SelectField, TextAreaField, TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useAuth } from '@/features/auth/useAuth';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type {
  ConfiguracionCorreo as Configuracion,
  ConfiguracionCorreoUpdate,
  SeguridadSmtp,
  VistaPreviaCorreo,
} from '@/types/api';

import estilos from './ConfiguracionCorreo.module.css';

const SEGURIDADES: readonly { valor: SeguridadSmtp; texto: string }[] = [
  { valor: 'starttls', texto: 'STARTTLS (587)' },
  { valor: 'ssl', texto: 'SSL/TLS (465)' },
  { valor: 'ninguna', texto: 'Sin cifrar' },
];

interface Borrador {
  host: string;
  puerto: string;
  seguridad: SeguridadSmtp;
  usuario: string;
  password: string;
  remitente_nombre: string;
  remitente_correo: string;
  destinatarios: string;
  max_adjunto_mb: string;
  dias_enlace: string;
  url_publica: string;
  plantilla_asunto: string;
  plantilla_cuerpo: string;
}

function borradorDe(config: Configuracion): Borrador {
  return {
    host: config.host,
    puerto: String(config.puerto),
    seguridad: config.seguridad,
    usuario: config.usuario,
    password: '',
    remitente_nombre: config.remitente_nombre,
    remitente_correo: config.remitente_correo,
    destinatarios: config.destinatarios_permitidos.join('\n'),
    max_adjunto_mb: String(config.max_adjunto_mb),
    dias_enlace: String(config.dias_enlace),
    url_publica: config.url_publica,
    plantilla_asunto: config.plantilla_asunto,
    plantilla_cuerpo: config.plantilla_cuerpo,
  };
}

function cambiosDe(borrador: Borrador): ConfiguracionCorreoUpdate {
  const cambios: ConfiguracionCorreoUpdate = {
    host: borrador.host.trim(),
    puerto: Number(borrador.puerto),
    seguridad: borrador.seguridad,
    usuario: borrador.usuario.trim(),
    remitente_nombre: borrador.remitente_nombre.trim(),
    remitente_correo: borrador.remitente_correo.trim(),
    destinatarios_permitidos: borrador.destinatarios
      .split(/[\s,;]+/)
      .map((c) => c.trim())
      .filter(Boolean),
    max_adjunto_mb: Number(borrador.max_adjunto_mb),
    dias_enlace: Number(borrador.dias_enlace),
    url_publica: borrador.url_publica.trim(),
    plantilla_asunto: borrador.plantilla_asunto,
    plantilla_cuerpo: borrador.plantilla_cuerpo,
  };
  // Vacía = «no la toques»: la guardada nunca vuelve al navegador.
  if (borrador.password) cambios.password = borrador.password;
  return cambios;
}

/**
 * Servidor SMTP, remitente y plantilla del correo que se envía al terminar una
 * solicitud. Se guarda en el servidor (no en variables de entorno) y solo lo
 * ven los administradores.
 */
export function ConfiguracionCorreo() {
  const config = useQuery({
    queryKey: ['configuracion-correo'],
    queryFn: obtenerConfiguracionCorreo,
  });

  if (config.isPending) return <Skeleton lineas={6} etiqueta="Cargando la configuración" />;
  if (config.isError) {
    return (
      <ErrorState
        titulo="No se pudo cargar la configuración del correo"
        texto={config.error instanceof ApiError ? config.error.message : 'Error inesperado.'}
      />
    );
  }
  // La key reinicia el formulario cuando llega una versión guardada nueva.
  return <Formulario key={JSON.stringify(config.data)} config={config.data} />;
}

function Formulario({ config }: { config: Configuracion }) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const { correo } = useAuth();
  const [borrador, setBorrador] = useState<Borrador>(() => borradorDe(config));
  const [previa, setPrevia] = useState<VistaPreviaCorreo | null>(null);
  const [destinatarioPrueba, setDestinatarioPrueba] = useState(correo ?? '');

  function poner<K extends keyof Borrador>(campo: K, valor: Borrador[K]) {
    setBorrador((actual) => ({ ...actual, [campo]: valor }));
  }

  const guardar = useMutation({
    mutationFn: (cambios: ConfiguracionCorreoUpdate) => guardarConfiguracionCorreo(cambios),
    onSuccess: (guardada) => {
      mostrar({ tono: 'exito', titulo: 'Configuración del correo guardada' });
      cliente.setQueryData(['configuracion-correo'], guardada);
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo guardar',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const previsualizar = useMutation({
    mutationFn: () => previsualizarCorreo(borrador.plantilla_asunto, borrador.plantilla_cuerpo),
    onSuccess: setPrevia,
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo generar la vista previa',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const probar = useMutation({
    mutationFn: (destinatario: string) => enviarCorreoPrueba(destinatario),
    onSuccess: (respuesta) => mostrar({ tono: 'exito', titulo: respuesta.mensaje }),
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo enviar la prueba',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  function alGuardar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    guardar.mutate(cambiosDe(borrador));
  }

  function insertar(variable: string) {
    poner('plantilla_cuerpo', `${borrador.plantilla_cuerpo}{{${variable}}}`);
  }

  return (
    <div className={layout.pilaAmplia}>
      <form className={layout.pilaAmplia} onSubmit={alGuardar} noValidate>
        <Panel
          titulo="Servidor SMTP"
          descripcion="Con Gmail: smtp.gmail.com, puerto 587 con STARTTLS y una contraseña de aplicación (Cuenta de Google › Seguridad), nunca la contraseña de la cuenta."
          acciones={
            <Badge tono={config.configurado ? 'exito' : 'aviso'} conPunto>
              {config.configurado ? 'Configurado' : 'Sin configurar'}
            </Badge>
          }
        >
          <div className={layout.rejillaFormulario}>
            <TextField
              etiqueta="Servidor (host)"
              name="host"
              value={borrador.host}
              onChange={(e) => poner('host', e.target.value)}
              placeholder="smtp.gmail.com"
              autoComplete="off"
            />
            <TextField
              etiqueta="Puerto"
              name="puerto"
              type="number"
              min={1}
              max={65535}
              value={borrador.puerto}
              onChange={(e) => poner('puerto', e.target.value)}
            />
            <SelectField
              etiqueta="Seguridad"
              name="seguridad"
              value={borrador.seguridad}
              onChange={(e) => poner('seguridad', e.target.value as SeguridadSmtp)}
              opciones={SEGURIDADES}
            />
            <TextField
              etiqueta="Usuario"
              name="usuario"
              value={borrador.usuario}
              onChange={(e) => poner('usuario', e.target.value)}
              autoComplete="off"
            />
            <TextField
              etiqueta="Contraseña"
              name="password"
              type="password"
              value={borrador.password}
              onChange={(e) => poner('password', e.target.value)}
              autoComplete="new-password"
              ayuda={
                config.password_configurada
                  ? 'Hay una contraseña guardada. Déjalo vacío para conservarla.'
                  : 'Todavía no hay ninguna guardada.'
              }
            />
          </div>
        </Panel>

        <Panel
          titulo="Remitente y envío"
          descripcion="Si el ZIP pasa del tamaño máximo, en vez de adjuntarlo se envía un enlace de descarga que caduca."
        >
          <div className={layout.rejillaFormulario}>
            <TextField
              etiqueta="Nombre del remitente"
              name="remitente_nombre"
              value={borrador.remitente_nombre}
              onChange={(e) => poner('remitente_nombre', e.target.value)}
            />
            <TextField
              etiqueta="Correo del remitente"
              name="remitente_correo"
              type="email"
              value={borrador.remitente_correo}
              onChange={(e) => poner('remitente_correo', e.target.value)}
              ayuda="Vacío = el mismo usuario SMTP."
            />
            <TextField
              etiqueta="Tamaño máximo del adjunto (MB)"
              name="max_adjunto_mb"
              type="number"
              min={1}
              max={25}
              value={borrador.max_adjunto_mb}
              onChange={(e) => poner('max_adjunto_mb', e.target.value)}
            />
            <TextField
              etiqueta="Días que vale el enlace"
              name="dias_enlace"
              type="number"
              min={1}
              max={30}
              value={borrador.dias_enlace}
              onChange={(e) => poner('dias_enlace', e.target.value)}
            />
            <TextField
              etiqueta="URL pública de Sire"
              name="url_publica"
              value={borrador.url_publica}
              onChange={(e) => poner('url_publica', e.target.value)}
              placeholder="https://sire.tudominio.pe"
              ayuda="Con ella se arman los enlaces de descarga. Sin ella, el ZIP grande se descarga desde el panel."
            />
          </div>
          <TextAreaField
            etiqueta="Destinatarios permitidos"
            name="destinatarios"
            rows={3}
            mono
            value={borrador.destinatarios}
            onChange={(e) => poner('destinatarios', e.target.value)}
            ayuda="Uno por línea. Si hay alguno, solo se escribe a esos correos (para pruebas); vacío = a cualquiera."
          />
        </Panel>

        <Panel
          titulo="Plantilla del mensaje"
          descripcion="Las variables entre llaves dobles se sustituyen en cada envío. El texto se envía tal cual y en HTML."
          acciones={
            <Button
              type="button"
              pequeno
              variante="fantasma"
              onClick={() => {
                poner('plantilla_asunto', config.plantilla_por_defecto.asunto);
                poner('plantilla_cuerpo', config.plantilla_por_defecto.cuerpo);
              }}
            >
              Restaurar plantilla por defecto
            </Button>
          }
        >
          <div className={layout.pila}>
            <TextField
              etiqueta="Asunto"
              name="plantilla_asunto"
              value={borrador.plantilla_asunto}
              onChange={(e) => poner('plantilla_asunto', e.target.value)}
            />
            <TextAreaField
              etiqueta="Cuerpo"
              name="plantilla_cuerpo"
              rows={12}
              mono
              value={borrador.plantilla_cuerpo}
              onChange={(e) => poner('plantilla_cuerpo', e.target.value)}
            />
            <ul className={estilos.variables} aria-label="Variables disponibles">
              {config.variables.map((variable) => (
                <li key={variable.nombre} className={estilos.variable}>
                  <Button
                    type="button"
                    pequeno
                    variante="secundario"
                    aria-label={`Insertar la variable ${variable.nombre}`}
                    onClick={() => insertar(variable.nombre)}
                  >
                    {`{{${variable.nombre}}}`}
                  </Button>
                  <span className={layout.textoSecundario}>{variable.descripcion}</span>
                </li>
              ))}
            </ul>
            <div className={layout.fila}>
              <Button
                type="button"
                variante="secundario"
                cargando={previsualizar.isPending}
                onClick={() => previsualizar.mutate()}
              >
                Vista previa
              </Button>
            </div>
            {previa ? (
              <div className={estilos.previa}>
                <p>
                  <strong>Asunto:</strong> {previa.asunto}
                </p>
                <iframe
                  title="Vista previa del correo"
                  className={estilos.marco}
                  sandbox=""
                  srcDoc={previa.html}
                />
              </div>
            ) : null}
          </div>
        </Panel>

        <div className={layout.filaFin}>
          <Button type="submit" variante="primario" cargando={guardar.isPending}>
            Guardar configuración
          </Button>
        </div>
      </form>

      <Panel
        titulo="Correo de prueba"
        descripcion="Usa la configuración guardada, con datos de ejemplo. Guarda antes los cambios que quieras probar."
      >
        <form
          className={estilos.prueba}
          onSubmit={(evento) => {
            evento.preventDefault();
            probar.mutate(destinatarioPrueba.trim());
          }}
          noValidate
        >
          <TextField
            etiqueta="Enviar a"
            name="destinatario_prueba"
            type="email"
            value={destinatarioPrueba}
            onChange={(e) => setDestinatarioPrueba(e.target.value)}
          />
          <Button
            type="submit"
            variante="secundario"
            cargando={probar.isPending}
            disabled={!destinatarioPrueba.trim()}
          >
            Enviar prueba
          </Button>
        </form>
      </Panel>
    </div>
  );
}
