import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { autorizarTelefono, crearLote, listarLotes, listarTelefonos } from '@/api/captura';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import layout from '@/styles/layouts.module.css';

export function LotesPage() {
  const ruc = useRuc();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [period, setPeriod] = useState('');
  const [phone, setPhone] = useState('');
  const batches = useQuery({
    queryKey: ['captura', ruc, 'batches', page],
    queryFn: () => listarLotes(page),
    refetchInterval: 5000,
  });
  const phones = useQuery({ queryKey: ['captura', ruc, 'phones'], queryFn: listarTelefonos });
  const create = useMutation({
    mutationFn: () => crearLote(period.replace('-', '')),
    onSuccess: async (batch) => {
      await navigate(`/lotes/${batch.id}`);
    },
  });
  const authorize = useMutation({
    mutationFn: ({ number, active }: { number: string; active: boolean }) =>
      autorizarTelefono(number, active),
    onSuccess: async () => {
      setPhone('');
      await client.invalidateQueries({ queryKey: ['captura', ruc, 'phones'] });
    },
  });
  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Lotes y WhatsApp"
        acciones={<Link to="/comprobantes">Inventario</Link>}
      />
      <div className={layout.bento}>
        <Panel titulo="Nuevo lote">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              create.mutate();
            }}
            className={layout.pila}
          >
            <TextField
              etiqueta="Periodo contable"
              type="month"
              required
              value={period}
              onChange={(event) => setPeriod(event.target.value)}
            />
            <Button type="submit" cargando={create.isPending}>
              Crear lote
            </Button>
            {create.error && <p role="alert">{create.error.message}</p>}
          </form>
        </Panel>
        <Panel
          titulo="Teléfono autorizado"
          descripcion="El número podrá registrar documentos para esta empresa por WhatsApp."
        >
          {phones.error && <p role="alert">{phones.error.message}</p>}
          {phones.isLoading && <p role="status">Cargando teléfonos…</p>}
          {phones.data
            ?.filter((item) => item.active)
            .map((item) => (
              <div className={layout.fila} key={item.phone}>
                <p>{item.phone}</p>
                <Button
                  disabled={authorize.isPending}
                  onClick={() => authorize.mutate({ number: item.phone, active: false })}
                >
                  Desactivar
                </Button>
              </div>
            ))}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              authorize.mutate({ number: phone, active: true });
            }}
            className={layout.pila}
          >
            <TextField
              etiqueta="Número con código de país"
              type="tel"
              required
              value={phone}
              placeholder="+519XXXXXXXX"
              onChange={(event) => setPhone(event.target.value)}
            />
            <Button type="submit" cargando={authorize.isPending}>
              Autorizar número
            </Button>
            {authorize.error && <p role="alert">{authorize.error.message}</p>}
          </form>
        </Panel>
      </div>
      <Panel titulo="Lotes recibidos">
        {batches.error && <p role="alert">{batches.error.message}</p>}
        {batches.isLoading && <p role="status">Cargando lotes…</p>}
        {!batches.isLoading && !batches.error && !batches.data?.length && <p>Aún no hay lotes en esta página.</p>}
        <ul>
          {batches.data?.map((batch) => (
            <li key={batch.id}>
              <Link to={`/lotes/${batch.id}`}>
                #{batch.id.slice(0, 8)} · {batch.accounting_period}
              </Link>{' '}
              · {batch.status} · Documentos: {batch.received_count} ·{' '}
              {new Date(batch.created_at).toLocaleDateString('es-PE')}
            </li>
          ))}
        </ul>
        <div className={layout.fila}>
          <Button disabled={page === 1} onClick={() => setPage(page - 1)}>
            Anterior
          </Button>
          <span>Página {page}</span>
          <Button disabled={(batches.data?.length ?? 0) < 25} onClick={() => setPage(page + 1)}>
            Siguiente
          </Button>
        </div>
      </Panel>
    </div>
  );
}
