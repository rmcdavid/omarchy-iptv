// scripts/dev-harness/spikes/state-literal-link/probe.cpp -- D-STATE-9: where
// Qt's QSaveFile (the FileView's atomic writer, D-SINK-103) writes through a
// state.json link, and whose mode it gives the file. The claims check of
// D-SINK-103 wrote the first version in its scratch on 2026-11-14; this copy
// moves the layout into measure.sh, so the shipping helper's `state private`
// can run between the layout and the save.
//
//   probe PATH FILE...
//
// Prints QFileInfo(PATH).symLinkTarget() and realpath(PATH), saves the text
// NEW through QSaveFile(PATH) -- open, write, commit, as the FileView does --
// and then, for each FILE, its mode and its first line, or `absent`. A FILE
// holding NEW is where the save landed; the kernel's answer for where the
// plugin READS is realpath's. No path is invented here: the driver names
// every file it wants read. Links against the installed libQt6Core.
//
//   probe --clean HEX...
//
// (D-STATE-9's guard, 2026-11-21.) For each argument, the UTF-8 text whose
// hex it is, prints `CLEAN <hex in> <hex out>`, out being QDir::cleanPath of
// it: the cleaning QSaveFile gives each hop of a link (the helper's
// qt_clean_path reimplements it, and tests/fixtures/qt-clean-path.json is
// this mode's output, which the python suite holds it to). Hex both ways,
// so no text needs quoting through the shell or gdb.
#include <QtCore/QByteArray>
#include <QtCore/QCoreApplication>
#include <QtCore/QDir>
#include <QtCore/QFileInfo>
#include <QtCore/QSaveFile>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/stat.h>

static void show(const char *path) {
    struct stat st;
    if (lstat(path, &st) != 0) {
        printf("  FILE %s absent\n", path);
        return;
    }
    if (S_ISLNK(st.st_mode)) {
        printf("  FILE %s link\n", path);
        return;
    }
    char buf[64] = {0};
    FILE *f = fopen(path, "r");
    if (f) {
        if (!fgets(buf, sizeof buf, f)) buf[0] = 0;
        fclose(f);
    }
    buf[strcspn(buf, "\n")] = 0;
    printf("  FILE %s mode %o text '%s'\n", path, (unsigned)(st.st_mode & 07777), buf);
}

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    if (argc < 2) {
        fprintf(stderr, "usage: probe PATH FILE... | probe --clean HEX...\n");
        return 2;
    }
    if (strcmp(argv[1], "--clean") == 0) {
        for (int i = 2; i < argc; ++i) {
            const QString in = QString::fromUtf8(QByteArray::fromHex(QByteArray(argv[i])));
            const QByteArray out = QDir::cleanPath(in).toUtf8().toHex();
            printf("CLEAN %s %s\n", argv[i], out.isEmpty() ? "-" : out.constData());
        }
        return 0;
    }
    const QString path = QString::fromLocal8Bit(argv[1]);
    char resolved[PATH_MAX];
    const char *real = realpath(argv[1], resolved);
    printf("  symLinkTarget %s\n", QFileInfo(path).symLinkTarget().toLocal8Bit().constData());
    printf("  realpath      %s\n", real ? real : "(none)");
    QSaveFile save(path);
    if (!save.open(QIODevice::WriteOnly)) {
        printf("  open failed: %s\n", save.errorString().toLocal8Bit().constData());
    } else {
        save.write("NEW\n");
        printf("  commit %d\n", save.commit() ? 1 : 0);
    }
    for (int i = 2; i < argc; ++i) show(argv[i]);
    return 0;
}
