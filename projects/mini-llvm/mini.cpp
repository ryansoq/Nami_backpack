//===----------------------------------------------------------------------===//
// mini.cpp — 極簡教學編譯器：一條加法看懂「前端 → LLVM IR」全流程
//
// 支援的語言（就這三種句型，夠了）：
//     a = 5
//     c = a + b
//     return c
//
// 流程（本檔由上到下就是編譯器的四站）：
//     原始碼 → [1] Lexer(字元→token) → [2] Parser(token→AST)
//            → [3] Codegen(AST→LLVM IR) → [4] 印出 IR / 存檔
//
// 編譯：  bash build.sh
// 執行：  ./mini program.mini        （會印 tokens、AST、IR）
// 跑 IR： /usr/lib/llvm-20/bin/lli out.ll ; echo $?   ← 看到 12 就是成功
//===----------------------------------------------------------------------===//

#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Verifier.h"
#include "llvm/Support/raw_ostream.h"
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <vector>

//===--------------------------------------------------------------------===//
// [1] LEXER — 把字元流切成 token 流
//
// 這個語言只需要 6 種 token。lexer 的工作就是「認字」：
// 看到數字連續讀完、看到字母連續讀完、看到 = 或 + 各自成一個 token。
//===--------------------------------------------------------------------===//

enum TokenKind { TK_IDENT, TK_NUMBER, TK_EQUAL, TK_PLUS, TK_RETURN, TK_EOF };

struct Token {
    TokenKind kind;
    std::string text;   // IDENT 的名字，或 NUMBER 的字面值
};

std::vector<Token> lex(const std::string &src) {
    std::vector<Token> toks;
    size_t i = 0;
    while (i < src.size()) {
        char c = src[i];
        if (isspace(c)) { i++; continue; }              // 跳過空白/換行
        if (isdigit(c)) {                                // 數字：一路吃到底
            std::string num;
            while (i < src.size() && isdigit(src[i])) num += src[i++];
            toks.push_back({TK_NUMBER, num});
        } else if (isalpha(c)) {                         // 字母：識別字或關鍵字
            std::string id;
            while (i < src.size() && isalnum(src[i])) id += src[i++];
            toks.push_back({id == "return" ? TK_RETURN : TK_IDENT, id});
        } else if (c == '=') { toks.push_back({TK_EQUAL, "="}); i++; }
        else if (c == '+')   { toks.push_back({TK_PLUS,  "+"}); i++; }
        else { std::cerr << "lex error: '" << c << "'\n"; exit(1); }
    }
    toks.push_back({TK_EOF, ""});
    return toks;
}

//===--------------------------------------------------------------------===//
// [2] PARSER — 把 token 流組裝成 AST（抽象語法樹）
//
// 文法（BNF，三條規則就是整個語言）：
//     stmt := IDENT '=' expr        （賦值）
//           | 'return' IDENT        （回傳）
//     expr := NUMBER                （常數）
//           | IDENT '+' IDENT       （加法）
//
// AST 節點也只需要四種。真實編譯器的 AST 是繼承體系；
// 這裡用一個 struct + kind 欄位，犧牲優雅換取一眼看懂。
//===--------------------------------------------------------------------===//

struct Expr {                       // 運算式：常數 或 a+b
    enum { NUM, ADD } kind;
    int num = 0;                    // kind==NUM 用
    std::string lhs, rhs;           // kind==ADD 用（兩個變數名）
};

struct Stmt {                       // 陳述式：賦值 或 return
    enum { ASSIGN, RETURN } kind;
    std::string target;             // ASSIGN 的目標變數 / RETURN 的變數
    Expr expr;                      // ASSIGN 的右手邊
};

std::vector<Stmt> parse(const std::vector<Token> &toks) {
    std::vector<Stmt> prog;
    size_t i = 0;
    auto expect = [&](TokenKind k, const char *what) {
        if (toks[i].kind != k) { std::cerr << "parse error: expected " << what << "\n"; exit(1); }
        return toks[i++];
    };
    while (toks[i].kind != TK_EOF) {
        if (toks[i].kind == TK_RETURN) {                 // return IDENT
            i++;
            Token v = expect(TK_IDENT, "identifier after return");
            prog.push_back({Stmt::RETURN, v.text, {}});
        } else {                                         // IDENT = expr
            Token name = expect(TK_IDENT, "identifier");
            expect(TK_EQUAL, "'='");
            Expr e;
            if (toks[i].kind == TK_NUMBER) {             // expr := NUMBER
                e.kind = Expr::NUM;
                e.num = std::stoi(toks[i++].text);
            } else {                                     // expr := IDENT + IDENT
                Token l = expect(TK_IDENT, "identifier");
                expect(TK_PLUS, "'+'");
                Token r = expect(TK_IDENT, "identifier");
                e.kind = Expr::ADD; e.lhs = l.text; e.rhs = r.text;
            }
            prog.push_back({Stmt::ASSIGN, name.text, e});
        }
    }
    return prog;
}

//===--------------------------------------------------------------------===//
// [3] CODEGEN — 走訪 AST，用 IRBuilder 吐出 LLVM IR
//
// 教學重點：變數怎麼表示？
// 學 clang -O0 的做法：每個變數配一塊 stack 記憶體（alloca），
// 賦值 = store，讀取 = load。這樣「不用想 SSA」就能生出正確的 IR —
// SSA 化交給後面的 mem2reg pass（試試 opt -passes=mem2reg out.ll）。
// 這正是真實編譯器的流程：前端無腦 alloca，中端 mem2reg 升級成 SSA。
//===--------------------------------------------------------------------===//

int main(int argc, char **argv) {
    // ── 讀原始碼 ──
    std::string path = argc > 1 ? argv[1] : "program.mini";
    std::ifstream f(path);
    if (!f) { std::cerr << "cannot open " << path << "\n"; return 1; }
    std::stringstream ss; ss << f.rdbuf();
    std::string src = ss.str();
    std::cout << "═══ 原始碼 ═══\n" << src << "\n";

    // ── [1] Lexer ──
    auto toks = lex(src);
    std::cout << "═══ [1] Tokens ═══\n";
    const char *names[] = {"IDENT", "NUMBER", "EQUAL", "PLUS", "RETURN", "EOF"};
    for (auto &t : toks)
        std::cout << "  (" << names[t.kind] << ", '" << t.text << "')\n";

    // ── [2] Parser ──
    auto prog = parse(toks);
    std::cout << "\n═══ [2] AST ═══\n";
    for (auto &s : prog) {
        if (s.kind == Stmt::RETURN)
            std::cout << "  Return(" << s.target << ")\n";
        else if (s.expr.kind == Expr::NUM)
            std::cout << "  Assign(" << s.target << ", Num(" << s.expr.num << "))\n";
        else
            std::cout << "  Assign(" << s.target << ", Add(" << s.expr.lhs
                      << ", " << s.expr.rhs << "))\n";
    }

    // ── [3] Codegen：LLVM 的三件套 ──
    llvm::LLVMContext ctx;                    // 所有 IR 物件的「宇宙」
    llvm::Module mod("mini", ctx);            // 一個編譯單元（≈ 一個 .c 檔）
    llvm::IRBuilder<> builder(ctx);           // 幫你「寫指令」的筆

    // 建 main 函式：i32 main()，加一個 entry basic block，把筆尖移過去
    auto *i32 = builder.getInt32Ty();
    auto *fnTy = llvm::FunctionType::get(i32, /*參數*/{}, /*可變參數*/false);
    auto *mainFn = llvm::Function::Create(
        fnTy, llvm::Function::ExternalLinkage, "main", mod);
    builder.SetInsertPoint(llvm::BasicBlock::Create(ctx, "entry", mainFn));

    // 符號表：變數名 → 它的 stack 位置（alloca 回傳的指標）
    std::map<std::string, llvm::Value *> vars;
    auto slot = [&](const std::string &name) {          // 沒見過的變數就開一格
        if (!vars.count(name))
            vars[name] = builder.CreateAlloca(i32, nullptr, name);
        return vars[name];
    };

    for (auto &s : prog) {
        if (s.kind == Stmt::ASSIGN) {
            llvm::Value *val;
            if (s.expr.kind == Expr::NUM) {
                val = builder.getInt32(s.expr.num);      // 常數直接做 immediate
            } else {
                // a + b：先把兩個變數從記憶體 load 出來，再 add
                auto *l = builder.CreateLoad(i32, slot(s.expr.lhs), s.expr.lhs);
                auto *r = builder.CreateLoad(i32, slot(s.expr.rhs), s.expr.rhs);
                val = builder.CreateAdd(l, r, s.target);
            }
            builder.CreateStore(val, slot(s.target));    // 存回目標變數
        } else {                                         // return x
            auto *v = builder.CreateLoad(i32, slot(s.target), s.target);
            builder.CreateRet(v);
        }
    }

    // 體檢：IR 結構是否合法（少 return、型別錯都會被抓）
    if (llvm::verifyModule(mod, &llvm::errs())) return 1;

    // ── [4] 輸出 ──
    std::cout << "\n═══ [3] LLVM IR ═══\n";
    std::cout.flush();               // std::cout 有緩衝、llvm::outs() 沒有 —
                                     // 不 flush 的話 IR 會插隊印在前面
    mod.print(llvm::outs(), nullptr);
    llvm::outs().flush();

    std::error_code ec;
    llvm::raw_fd_ostream out("out.ll", ec);
    mod.print(out, nullptr);
    std::cout << "\n已存 out.ll — 接著玩：\n"
              << "  跑起來:   /usr/lib/llvm-20/bin/lli out.ll ; echo $?\n"
              << "  看SSA化:  /usr/lib/llvm-20/bin/opt -passes=mem2reg -S out.ll\n";
    return 0;
}
