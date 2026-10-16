"""Write editable, relative-path native compiler/kernel build manifests."""


def install(snapshot, work):
    for name, source, output in [('compiler', 'compiler.build', 'compiler.elf'),
                                  ('kernel', 'kernel/kernel.build', 'kernel.elf')]:
        lines = []
        for line in (snapshot / source).read_text().splitlines():
            if line.startswith(('source ', 'assembly ')):
                kind, path = line.split(' ', 1)
                if not (work / 'system' / path).is_file():
                    raise ValueError('native source not shipped: ' + path)
                lines.append(kind + ' system/' + path)
            elif line.startswith('output '):
                lines.append('output ' + output)
            else:
                lines.append(line)
        (work / (name + '.build')).write_text('\n'.join(lines) + '\n')
