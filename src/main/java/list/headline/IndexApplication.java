package list.headline;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IndexApplication {

    public static void main(String[] args) {
        SpringApplication.run(IndexApplication.class, args);
    }

    @Bean
    public CommandLineRunner run(IndexService indexService) {
        return args -> {
            try {
                String indexHtml = indexService.getIndexHtml();
                System.out.println("=== 지수 HTML 출력 ===");
                System.out.println(indexHtml);
            } catch (Exception e) {
                System.err.println("에러 발생: " + e.getMessage());
                e.printStackTrace();
            }
        };
    }
}
