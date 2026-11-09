-- =====================================================================
-- Plataforma de adopción responsable de mascotas
-- Fundación Huellas de Esperanza
-- Ejecutar completo en Supabase > SQL Editor
-- =====================================================================

-- Limpieza (por si se ejecuta de nuevo)
drop table if exists solicitudes;
drop table if exists mascotas;

-- ---------------------------------------------------------------------
-- Tabla dueña: API 1 (Mascotas)
-- Ningún otro servicio escribe en esta tabla.
-- ---------------------------------------------------------------------
create table mascotas (
  id           bigint generated always as identity primary key,
  nombre       text not null check (char_length(nombre) between 1 and 60),
  especie      text not null check (especie in ('perro', 'gato', 'otro')),
  raza         text,
  sexo         text check (sexo in ('macho', 'hembra')),
  edad_meses   int  check (edad_meses between 0 and 400),
  descripcion  text,
  foto_url     text,
  estado       text not null default 'disponible'
               check (estado in ('disponible', 'en_proceso', 'adoptada')),
  creado_en    timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);

create index idx_mascotas_estado on mascotas (estado);

-- ---------------------------------------------------------------------
-- Tabla dueña: API 2 (Adopciones)
-- mascota_id NO tiene llave foránea hacia mascotas: cada servicio es
-- dueño de sus datos y la existencia de la mascota se verifica por HTTP
-- contra la API de Mascotas.
-- ---------------------------------------------------------------------
create table solicitudes (
  id                 bigint generated always as identity primary key,
  mascota_id         bigint not null,
  nombre_solicitante text   not null,
  documento          text   not null,
  email              text   not null,
  telefono           text   not null,
  ciudad             text,
  motivo             text   not null,
  estado             text   not null default 'pendiente'
                     check (estado in ('pendiente', 'aprobada', 'rechazada')),
  observacion        text,
  creado_en          timestamptz not null default now(),
  actualizado_en     timestamptz not null default now()
);

create index idx_solicitudes_mascota on solicitudes (mascota_id);
create index idx_solicitudes_estado  on solicitudes (estado);

-- Regla de negocio garantizada por la base de datos:
-- una mascota no puede tener dos solicitudes aprobadas.
-- Si dos aprobaciones llegan al mismo tiempo, la segunda falla con 23505.
create unique index una_aprobada_por_mascota
  on solicitudes (mascota_id)
  where estado = 'aprobada';

-- Una persona no puede tener dos solicitudes pendientes para la misma mascota
create unique index una_pendiente_por_persona
  on solicitudes (mascota_id, documento)
  where estado = 'pendiente';

-- ---------------------------------------------------------------------
-- Seguridad: RLS activado y sin políticas.
-- Con esto la anon key (pública) no puede leer ni escribir nada.
-- Las APIs usan la service_role key, que sí tiene acceso.
-- ---------------------------------------------------------------------
alter table mascotas    enable row level security;
alter table solicitudes enable row level security;

-- ---------------------------------------------------------------------
-- Datos iniciales
-- ---------------------------------------------------------------------
insert into mascotas (nombre, especie, raza, sexo, edad_meses, descripcion) values
 ('Luna',    'perro', 'Criolla',          'hembra', 18, 'Juguetona y buena con niños. Esterilizada y vacunada.'),
 ('Michi',   'gato',  'Siamés',           'macho',   8, 'Tranquilo, le gusta dormir al sol. Usa arenero.'),
 ('Rocky',   'perro', 'Labrador mestizo', 'macho',  36, 'Mucha energía, necesita patio y paseos diarios.'),
 ('Canela',  'perro', 'Beagle mestiza',   'hembra', 60, 'Adulta, calmada, ideal para apartamento.'),
 ('Pelusa',  'gato',  'Angora mestiza',   'hembra', 14, 'Rescatada de la calle, algo tímida al principio.'),
 ('Tambor',  'otro',  'Conejo',           'macho',  10, 'Come heno y verduras. Necesita espacio para saltar.');
