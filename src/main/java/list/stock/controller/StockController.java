package list.stock.controller;

import list.stock.dto.Stock;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

//test2
@RestController
@RequestMapping("/api/stocks")
@CrossOrigin(origins = "http://localhost:3000")
public class StockController {

    @GetMapping("/volume-top10")
    public List<Stock> getTopByVolume() throws IOException {
        return fetchStocks("https://finance.naver.com/sise/nxt_sise_quant.naver?sosok=0");
    }

    @GetMapping("/marketcap-top10")
    public List<Stock> getTopByMarketCap() throws IOException {
        return fetchStocks("https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1");
    }

    @GetMapping("/rising-top10")
    public List<Stock> getTopRising() throws IOException {
        return fetchStocks("https://finance.naver.com/sise/sise_rise.naver");
    }

    @GetMapping("/falling-top10")
    public List<Stock> getTopFalling() throws IOException {
        return fetchStocks("https://finance.naver.com/sise/sise_fall.naver");
    }

    private List<Stock> fetchStocks(String url) throws IOException {
        List<Stock> stockList = new ArrayList<>();
        Document doc = Jsoup.connect(url).get();
        Elements rows = doc.select("table.type_2 tr");

        int count = 0;
        for (Element row : rows) {
            Elements cols = row.select("td");
            if (cols.size() > 4 && count < 10) {
                String name = cols.get(1).text();
                String price = cols.get(2).text();
                String changeRate = cols.get(4).text();

                stockList.add(new Stock(name, price, changeRate));
                count++;
            }
        }

        return stockList;
    }

}
