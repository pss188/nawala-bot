package main

import (
	"bufio"
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/H0llyW00dzZ/nawala-checker/src/nawala"
	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

func main() {
	// Baca token dari environment variable
	token := os.Getenv("TOKEN")
	if token == "" {
		log.Fatal("TOKEN environment variable is required")
	}

	// Chat ID untuk mengirim laporan
	chatID := os.Getenv("CHAT_ID")
	if chatID == "" {
		log.Fatal("CHAT_ID environment variable is required")
	}

	// Setup bot
	bot, err := tgbotapi.NewBotAPI(token)
	if err != nil {
		log.Fatal("Failed to create bot:", err)
	}

	// Setup Nawala checker
	checker := nawala.New(
		nawala.WithTimeout(10*time.Second),
		nawala.WithCacheTTL(5*time.Minute),
		nawala.WithConcurrency(50),
	)

	log.Printf("✅ Bot %s started", bot.Self.UserName)
	log.Println("📋 Mode: DNS Checker via Nawala SDK")

	// Kirim status awal
	sendStatus(bot, chatID, checker)

	// Jalankan pengecekan pertama
	runCheck(bot, chatID, checker)

	// Schedule: cek setiap 15 menit
	ticker := time.NewTicker(15 * time.Minute)
	defer ticker.Stop()

	log.Println("🔄 Bot will check domains every 15 minutes")

	for range ticker.C {
		runCheck(bot, chatID, checker)
	}
}

func sendStatus(bot *tgbotapi.BotAPI, chatID string, checker *nawala.Checker) {
	domains := bacaDomain()
	domainCount := len(domains)

	msg := tgbotapi.NewMessage(parseChatID(chatID), fmt.Sprintf(
		"🤖 *Nawala Checker Bot (Go)*\n\n"+
			"✅ **Status:** Aktif & Berjalan\n"+
			"📊 **Domain:** %d domain terdaftar\n"+
			"🔢 **Mode:** Concurrent DNS Query\n"+
			"🔑 **Network:** Indonesian Network Required\n"+
			"🌐 **SDK:** nawala-checker v0.7.1\n\n"+
			"_Bot akan mengecek domain setiap 15 menit_",
		domainCount,
	))
	msg.ParseMode = "Markdown"

	if _, err := bot.Send(msg); err != nil {
		log.Printf("Error sending status: %v", err)
	}
}

func runCheck(bot *tgbotapi.BotAPI, chatID string, checker *nawala.Checker) {
	log.Println("=" + strings.Repeat("=", 59))
	log.Println("🔄 MEMULAI PEMERIKSAAN NAWALA VIA SDK")
	log.Println("=" + strings.Repeat("=", 59))

	domains := bacaDomain()
	if len(domains) == 0 {
		log.Println("⚠️ Tidak ada domain untuk dicek")
		return
	}

	log.Printf("📋 Jumlah domain: %d", len(domains))

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	startTime := time.Now()
	results, err := checker.Check(ctx, domains...)
	elapsed := time.Since(startTime)

	if err != nil {
		log.Printf("❌ Error checking domains: %v", err)
		sendErrorReport(bot, chatID, err)
		return
	}

	log.Printf("⏱️ Waktu pemrosesan: %.2f detik", elapsed.Seconds())

	var blockedResults []nawala.Result
	for _, r := range results {
		if r.Blocked {
			blockedResults = append(blockedResults, r)
			log.Printf("🚫 %s: DIBLOKIR (server: %s)", r.Domain, r.Server)
		} else {
			log.Printf("✅ %s: AMAN", r.Domain)
		}
	}

	log.Printf("📊 Hasil: %d dari %d domain terblokir", len(blockedResults), len(domains))
	log.Println("✅ Pemeriksaan selesai")
	log.Println("=" + strings.Repeat("=", 60))

	sendReport(bot, chatID, results, len(domains))
}

func sendReport(bot *tgbotapi.BotAPI, chatID string, results []nawala.Result, total int) {
	var blocked []string
	for _, r := range results {
		if r.Blocked {
			blocked = append(blocked, r.Domain)
		}
	}

	chatIDInt := parseChatID(chatID)

	if len(blocked) == 0 {
		msg := tgbotapi.NewMessage(chatIDInt,
			"✅ *LAPORAN CEK NAWALA*\n\n"+
				"**SEMUA DOMAIN AMAN!** 🎉\n\n"+
				fmt.Sprintf("📊 **Total Domain:** %d\n", total)+
				fmt.Sprintf("⏰ **Waktu:** %s\n", time.Now().Format("02-01-2006 15:04:05"))+"\n"+
				"_Tidak ada domain yang terblokir._",
		)
		msg.ParseMode = "Markdown"
		bot.Send(msg)
		log.Printf("📤 Laporan aman: %d domain", total)
		return
	}

	var domainList string
	for i, domain := range blocked {
		if i >= 30 {
			domainList += fmt.Sprintf("\n... dan %d lainnya", len(blocked)-30)
			break
		}
		domainList += fmt.Sprintf("%d. 🚫 `%s`\n", i+1, domain)
	}

	msg := tgbotapi.NewMessage(chatIDInt, fmt.Sprintf(
		"❌❌❌❌❌❌❌❌❌\n\n"+
			"**%d DOMAIN TERBLOKIR**\n\n"+
			"%s\n"+
			"📊 **Statistik:** %d/%d domain terblokir\n"+
			"⏰ **Waktu:** %s\n\n"+
			"_Sumber: nawala-checker SDK_",
		len(blocked),
		domainList,
		len(blocked),
		total,
		time.Now().Format("02-01-2006 15:04:05"),
	))
	msg.ParseMode = "Markdown"

	if _, err := bot.Send(msg); err != nil {
		log.Printf("Error sending report: %v", err)
	}
}

func sendErrorReport(bot *tgbotapi.BotAPI, chatID string, err error) {
	msg := tgbotapi.NewMessage(parseChatID(chatID), fmt.Sprintf(
		"❌ *ERROR*\n\n"+
			"Gagal melakukan pengecekan domain:\n\n"+
			"`%v`\n\n"+
			"⏰ **Waktu:** %s",
		err,
		time.Now().Format("02-01-2006 15:04:05"),
	))
	msg.ParseMode = "Markdown"
	bot.Send(msg)
}

func bacaDomain() []string {
	domains := []string{}

	file, err := os.Open("domain.txt")
	if err != nil {
		log.Printf("❌ File domain.txt tidak ditemukan: %v", err)
		return domains
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		domain := strings.ToLower(line)
		for _, prefix := range []string{"http://", "https://", "www."} {
			domain = strings.TrimPrefix(domain, prefix)
		}
		domain = strings.TrimSuffix(domain, "/")
		if strings.Contains(domain, ".") && len(domain) > 3 {
			domains = append(domains, domain)
		}
	}

	if len(domains) > 0 {
		log.Printf("📖 Membaca %d domain dari domain.txt", len(domains))
	} else {
		log.Println("⚠️ Tidak ada domain ditemukan di domain.txt")
	}

	return domains
}

func parseChatID(chatID string) int64 {
	var id int64
	fmt.Sscanf(chatID, "%d", &id)
	return id
}
