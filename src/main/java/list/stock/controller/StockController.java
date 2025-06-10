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

//test
@RestController
@RequestMapping("/api/stocks")
@CrossOrigin(origins = "http://localhost:3000")
public class StockController {

    @GetMapping("/top10")
    public List<Stock> getTopStocks() throws IOException {
        List<Stock> stockList = new ArrayList<>();
        String url = "https://finance.naver.com/sise/nxt_sise_quant.naver?sosok=0";
        Document doc = Jsoup.connect(url).get();

        System.out.println("페이지 로딩 완료");

        Elements rows = doc.select("table.type_2 tr");
        System.out.println("행 수: " + rows.size());

        int count = 0;
        for (Element row : rows) {
            Elements cols = row.select("td");
            if (cols.size() > 0 && count < 10) {
                String name = cols.get(1).text();
                String price = cols.get(2).text();
                String changeRate = cols.get(6).text();

                Stock stock = new Stock(name, price, changeRate);
                stockList.add(stock);

                System.out.println(stock);
                count++;
            }
        }

        return stockList;
    }
}
