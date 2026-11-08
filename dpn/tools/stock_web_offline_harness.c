/* SPDX-License-Identifier: GPL-2.0-only */
/* Offline AArch64/QEMU harness for the extracted vendor library.
 * No dlopen, no vendor init routines, no device/network access.
 * MTD writer and memory-query entries are replaced before execution;
 * command/file imports are inert stubs. Unknown imports terminate.
 * This tests vendor parsing/dispatch, NOT physical NAND writes.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <elf.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/mman.h>

static uintptr_t guard = 0x1122334455667788ULL;
static unsigned writes, commands;
static int current_slot, boot_rc;
static int writer_rc;
static const char *current_version = "1.2";
static void unknown(void) { fputs("UNEXPECTED IMPORT\n", stderr); exit(90); }
static int quiet(void) { return 0; }
static int get_partition(int *slot) { *slot = current_slot; return boot_rc; }
static int dispatch_main(void *p, unsigned len) {
    (void)p; printf("HTTP_TARGET slot=0 bytes=%u\n", len); return 0;
}
static int dispatch_slave(void *p, unsigned len) {
    (void)p; printf("HTTP_TARGET slot=1 bytes=%u\n", len); return 0;
}
static int no_reboot(void *p) { (void)p; puts("REBOOT_STUB"); return 0; }
static void no_free(void *p) { (void)p; }
static int get_version(char *p) { strcpy(p, current_version); return 0; }
static int no_system(const char *cmd) {
    printf("COMMAND_STUB %s\n", cmd); commands++; return 0;
}
static int no_cms_system(const char *fn, int line, const char *cmd) {
    (void)fn; (void)line; return no_system(cmd);
}
static FILE *no_fopen(const char *p, const char *mode) {
    printf("FOPEN_DENIED %s %s\n", p, mode); return NULL;
}
static int memory_stub(unsigned long *a, unsigned long *b) {
    *a = *b = 512UL * 1024 * 1024; return 0;
}
static int writer_stub(const char *part, const void *data, size_t len) {
    const unsigned char *b = data;
    printf("WRITE_STUB partition=%s bytes=%zu first=%02x\n", part, len, len ? b[0] : 0);
    writes++;
    return writer_rc;
}
static uintptr_t resolve(const char *s) {
#define SYM(n) if (!strcmp(s, #n)) return (uintptr_t)&n
    SYM(memcpy); SYM(memset); SYM(memcmp); SYM(strcmp); SYM(strcasecmp);
    SYM(strncmp); SYM(strlen); SYM(strcpy); SYM(strncpy); SYM(strstr);
    SYM(strchr); SYM(sprintf); SYM(snprintf); SYM(sscanf); SYM(malloc); SYM(free);
    SYM(printf); SYM(puts); SYM(putchar); SYM(fputs); SYM(fprintf);
    SYM(ntohl); SYM(htonl);
#undef SYM
    if (!strcmp(s, "__stack_chk_guard")) return (uintptr_t)&guard;
    if (!strcmp(s, "__stack_chk_fail")) return (uintptr_t)&unknown;
    if (!strcmp(s, "system")) return (uintptr_t)&no_system;
    if (!strcmp(s, "cmsUtl_doSystem")) return (uintptr_t)&no_cms_system;
    if (!strcmp(s, "fopen")) return (uintptr_t)&no_fopen;
    if (!strcmp(s, "devCtl_getCurrentBootPartition")) return (uintptr_t)&get_partition;
    if (!strcmp(s, "devCtl_writeImageBuf")) return (uintptr_t)&dispatch_main;
    if (!strcmp(s, "devCtl_writeImageBufSlave")) return (uintptr_t)&dispatch_slave;
    if (!strcmp(s, "cmsMem_free")) return (uintptr_t)&no_free;
    if (!strcmp(s, "cmsUtil_sendRequestRebootMsg")) return (uintptr_t)&no_reboot;
    if (!strcmp(s, "sleep") || !strcmp(s, "__devCtl_log") || !strcmp(s, "log_log"))
        return (uintptr_t)&quiet;
    return (uintptr_t)&unknown;
}
static unsigned char *readfile(const char *path, size_t *len) {
    FILE *f = fopen(path, "rb"); if (!f) { perror(path); exit(91); }
    fseek(f, 0, SEEK_END); long n = ftell(f); rewind(f);
    if (n < 0) exit(92);
    unsigned char *b = malloc((size_t)n + 4096);
    memset(b + n, 0, 4096); /* valid fixtures only; not a memory-safety fuzzer */
    if (fread(b, 1, n, f) != (size_t)n) exit(93);
    fclose(f); *len = n; return b;
}
static void hook(unsigned char *p, uintptr_t fn) {
    /* ldr x16, PC+8; br x16; .quad target */
    uint32_t insn[] = {0x58000050, 0xd61f0200};
    memcpy(p, insn, 8); memcpy(p + 8, &fn, 8);
    __builtin___clear_cache((char *)p, (char *)p + 16);
}
int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: harness vendor-ELF synthetic.bin [write:SLOT|post:CURRENT:RC:TYPE|version:CURRENT] [fail]\n"); return 2; }
    if (argc>4 && !strcmp(argv[4], "fail")) writer_rc=-1;
    size_t n; unsigned char *file = readfile(argv[1], &n);
    Elf64_Ehdr *eh = (void *)file;
    if (n < sizeof(*eh) || memcmp(eh->e_ident, ELFMAG, 4) || eh->e_machine != EM_AARCH64) return 3;
    Elf64_Phdr *ph = (void *)(file + eh->e_phoff); size_t max = 0;
    for (int i=0; i<eh->e_phnum; i++) if (ph[i].p_type == PT_LOAD) {
        size_t end = ph[i].p_vaddr + ph[i].p_memsz; if (end > max) max = end;
    }
    unsigned char *base = mmap(NULL, (max + 4095) & ~4095UL, PROT_READ|PROT_WRITE|PROT_EXEC,
                               MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
    if (base == MAP_FAILED) return 4;
    for (int i=0; i<eh->e_phnum; i++) if (ph[i].p_type == PT_LOAD)
        memcpy(base + ph[i].p_vaddr, file + ph[i].p_offset, ph[i].p_filesz);
    Elf64_Shdr *sh = (void *)(file + eh->e_shoff);
    if (eh->e_type == ET_EXEC) {
        /* Original non-PIE httpd has local absolute pointers in .got. */
        char *names = (void *)(file + sh[eh->e_shstrndx].sh_offset);
        for (int i=0; i<eh->e_shnum; i++) if (!strncmp(names+sh[i].sh_name, ".got", 4)) {
            for (size_t j=0; j+8<=sh[i].sh_size; j+=8) {
                uintptr_t *p=(void *)(base+sh[i].sh_addr+j);
                if (*p>=0x400000 && *p<max) *p+=(uintptr_t)base;
            }
        }
    }
    for (int i=0; i<eh->e_shnum; i++) if (sh[i].sh_type == SHT_RELA) {
        Elf64_Rela *r = (void *)(file + sh[i].sh_offset);
        Elf64_Shdr *ss = &sh[sh[i].sh_link]; Elf64_Sym *sy = (void *)(file + ss->sh_offset);
        char *str = (void *)(file + sh[ss->sh_link].sh_offset);
        for (size_t j=0; j<sh[i].sh_size/sizeof(*r); j++) {
            unsigned type = ELF64_R_TYPE(r[j].r_info); unsigned k = ELF64_R_SYM(r[j].r_info);
            uintptr_t value;
            if (type == R_AARCH64_RELATIVE) value = (uintptr_t)base + r[j].r_addend;
            else if (type == R_AARCH64_GLOB_DAT || type == R_AARCH64_JUMP_SLOT || type == R_AARCH64_ABS64) {
                value = sy[k].st_shndx != SHN_UNDEF ? (uintptr_t)base + sy[k].st_value : resolve(str + sy[k].st_name);
                value += r[j].r_addend;
            } else { fprintf(stderr, "unsupported relocation %u\n", type); return 5; }
            memcpy(base + r[j].r_offset, &value, 8);
        }
    }
    size_t len; unsigned char *buf = readfile(argv[2], &len);
    if (eh->e_type == ET_EXEC) {
        if (argc>3 && !strncmp(argv[3], "version:", 8)) {
            current_version=argv[3]+8;
            hook(base+0x413d48, (uintptr_t)&get_version);
            int (*check)(void *)=(void *)(base+0x413e48);
            printf("VERSION_RC %d\n", check(buf)); return 0;
        }
        int type=3;
        if (argc<4 || sscanf(argv[3], "post:%d:%d:%d", &current_slot, &boot_rc, &type)!=3) return 6;
        memcpy(base+0x4578e0, &buf, 8);
        unsigned size=len; memcpy(base+0x4578d8, &size, 4);
        void (*post)(int)=(void *)(base+0x4145c4);
        post(type); return 0;
    }
    hook(base + 0xbf20, (uintptr_t)&writer_stub);
    hook(base + 0xc308, (uintptr_t)&memory_stub);
    hook(base + 0x5384, (uintptr_t)&quiet); /* internal vendor logger */
    int (*validate)(void *, unsigned) = (void *)(base + 0x590c);
    int rc = validate(buf, len); printf("VALIDATE_RC %d\n", rc);
    if (argc > 3 && !rc) {
        int slot = !strcmp(argv[3], "write:1");
        int (*writebuf)(void *, unsigned, int, int) = (void *)(base + 0xcaf0);
        rc = writebuf(buf, len, slot, 1);
        printf("WRITE_DISPATCH_RC %d writes=%u commands=%u\n", rc, writes, commands);
    }
    return 0;
}
